"""Aiohttp-powered built-in debug and administration consoles."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shutil
import sys
import time
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import tomlkit
from aiohttp import web

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.schemas.bot import BotConfig, Console
from neobot_app.console.security import (
    CredentialStore,
    LoginLimiter,
    Session,
    SessionStore,
    is_loopback,
    mask_secret,
    redact,
    validate_password,
)
from neobot_app.core import CONFIG_BACKUP_DIR, CONFIG_FILE, ENV_FILE


_COOKIE_NAME = "neobot_console_session"
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_ENV_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|authorization)"
)
_STATIC_DIR = Path(__file__).with_name("static")
_ROLE_KEY = web.AppKey("console_role", str)


class ConsoleService:
    """Owns the public debug console and loopback-only administration console."""

    def __init__(
        self,
        *,
        config: Any,
        data_dir: Path,
        logger: Any,
        group_queue: Any = None,
        friend_queue: Any = None,
        service_probe: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.data_dir = data_dir
        self.logger = logger
        settings = getattr(config, "console", None)
        timeout_minutes = int(getattr(settings, "session_timeout_minutes", 60))
        self.credentials = CredentialStore(data_dir / "console" / "auth.json")
        self.sessions = SessionStore(timeout_seconds=timeout_minutes * 60)
        self.login_limiter = LoginLimiter()
        self.group_queue = group_queue
        self.friend_queue = friend_queue
        self.service_probe = service_probe
        self.started_at = time.time()
        self.application: Any = None
        self.public_url: str | None = None
        self.admin_url: str | None = None
        self._runners: list[web.AppRunner] = []
        self._sites: list[web.BaseSite] = []
        self._config_lock = asyncio.Lock()

    def bind_application(self, application: Any) -> None:
        self.application = application

    async def start(self) -> None:
        settings = getattr(self.config, "console", None)
        if settings is None:
            return
        limit = max(1, min(100, int(getattr(settings, "port_search_limit", 100))))
        if bool(getattr(settings, "admin_enabled", True)):
            port = await self._start_site(
                role="admin",
                host="127.0.0.1",
                preferred_port=int(getattr(settings, "admin_port", 9891)),
                limit=limit,
            )
            self.admin_url = f"http://127.0.0.1:{port}"
            self.logger.info("管理员控制台已启动", url=self.admin_url)
        if bool(getattr(settings, "enabled", False)):
            host = str(getattr(settings, "host", "0.0.0.0") or "0.0.0.0")
            port = await self._start_site(
                role="debug",
                host=host,
                preferred_port=int(getattr(settings, "port", 9981)),
                limit=limit,
            )
            display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
            self.public_url = f"http://{display_host}:{port}"
            self.logger.info("调试控制台已启动", url=self.public_url, listen_host=host)

    async def stop(self) -> None:
        for runner in reversed(self._runners):
            try:
                await runner.cleanup()
            except Exception as exc:
                self.logger.warning("控制台关闭失败", error=str(exc))
        self._sites.clear()
        self._runners.clear()
        self.public_url = None
        self.admin_url = None

    async def _start_site(
        self,
        *,
        role: str,
        host: str,
        preferred_port: int,
        limit: int,
    ) -> int:
        if preferred_port < 1 or preferred_port > 65535:
            raise ValueError(f"控制台端口超出范围: {preferred_port}")
        app = self._make_app(role)
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=5)
        await runner.setup()
        last_error: OSError | None = None
        for offset in range(limit):
            port = preferred_port + offset
            if port > 65535:
                break
            site = web.TCPSite(
                runner,
                host=host,
                port=port,
            )
            try:
                await site.start()
            except OSError as exc:
                last_error = exc
                continue
            self._runners.append(runner)
            self._sites.append(site)
            return port
        await runner.cleanup()
        message = f"从端口 {preferred_port} 开始的 {limit} 个端口均不可用"
        if last_error is not None:
            message = f"{message}: {last_error}"
        raise OSError(message)

    def _make_app(self, role: str) -> web.Application:
        app = web.Application(
            middlewares=[self._security_middleware, self._local_admin_middleware],
            client_max_size=1024 * 1024,
        )
        app[_ROLE_KEY] = role
        app.on_response_prepare.append(self._prepare_headers)
        app.router.add_get("/", self._index)
        app.router.add_get("/assets/app.js", self._javascript)
        app.router.add_get("/assets/styles.css", self._stylesheet)
        app.router.add_get("/healthz", self._healthz)
        app.router.add_get("/api/auth/status", self._auth_status)
        app.router.add_post("/api/auth/setup", self._auth_setup)
        app.router.add_post("/api/auth/login", self._auth_login)
        app.router.add_post("/api/auth/logout", self._auth_logout)
        app.router.add_post("/api/auth/password", self._change_password)
        app.router.add_get("/api/overview", self._overview)
        app.router.add_get("/api/services", self._services)
        app.router.add_get("/api/tasks", self._tasks)
        app.router.add_get("/api/logs", self._logs)
        app.router.add_get("/api/logs/stream", self._log_stream)
        app.router.add_get("/api/debug-files", self._debug_files)
        app.router.add_get("/api/diagnostics", self._diagnostics)
        app.router.add_get("/api/diagnostics/export", self._diagnostics_export)
        app.router.add_get("/api/admin/config", self._admin_config)
        app.router.add_patch("/api/admin/config", self._admin_update_config)
        app.router.add_get("/api/admin/environment", self._admin_environment)
        app.router.add_put("/api/admin/environment/{key}", self._admin_update_environment)
        app.router.add_delete("/api/admin/environment/{key}", self._admin_delete_environment)
        return app

    @web.middleware
    async def _security_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Any],
    ) -> web.StreamResponse:
        public_paths = {
            "/",
            "/assets/app.js",
            "/assets/styles.css",
            "/healthz",
            "/api/auth/status",
            "/api/auth/setup",
            "/api/auth/login",
        }
        session: Session | None = None
        if request.path not in public_paths:
            session = self.sessions.get(request.cookies.get(_COOKIE_NAME))
            if session is None:
                return self._json_error("需要登录", status=401)
            request["console_session"] = session
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                supplied = request.headers.get("X-CSRF-Token", "")
                if not supplied or not secrets_compare(supplied, session.csrf_token):
                    return self._json_error("CSRF 校验失败", status=403)
                origin = request.headers.get("Origin")
                if origin and urlsplit(origin).netloc.casefold() != request.host.casefold():
                    return self._json_error("请求来源不可信", status=403)
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        except json.JSONDecodeError:
            response = self._json_error("请求体不是有效 JSON", status=400)
        except Exception as exc:
            self.logger.exception("控制台请求失败", path=request.path, error=str(exc))
            response = self._json_error("服务器处理请求失败", status=500)
        return response

    @web.middleware
    async def _local_admin_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Any],
    ) -> web.StreamResponse:
        role = request.app[_ROLE_KEY]
        peer = self._client_ip(request)
        if role == "admin" and not is_loopback(peer):
            return self._json_error("管理员控制台仅允许本机访问", status=403)
        if request.path.startswith("/api/admin/") and role != "admin":
            return self._json_error("此功能仅在本机管理员控制台提供", status=403)
        return await handler(request)

    async def _index(self, request: web.Request) -> web.Response:
        return web.FileResponse(_STATIC_DIR / "index.html")

    async def _javascript(self, request: web.Request) -> web.Response:
        return web.FileResponse(_STATIC_DIR / "app.js")

    async def _stylesheet(self, request: web.Request) -> web.Response:
        return web.FileResponse(_STATIC_DIR / "styles.css")

    async def _healthz(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "service": "NeoBot Console",
                "role": request.app[_ROLE_KEY],
                "configured": self.credentials.configured,
            }
        )

    async def _auth_status(self, request: web.Request) -> web.Response:
        session = self.sessions.get(request.cookies.get(_COOKIE_NAME))
        return web.json_response(
            {
                "configured": self.credentials.configured,
                "authenticated": session is not None,
                "setup_allowed": is_loopback(self._client_ip(request)),
                "role": request.app[_ROLE_KEY],
                "csrf_token": session.csrf_token if session else None,
                "session_timeout_seconds": self.sessions.timeout_seconds,
            }
        )

    async def _auth_setup(self, request: web.Request) -> web.Response:
        if self.credentials.configured:
            return self._json_error("控制台密码已经设置", status=409)
        if not is_loopback(self._client_ip(request)):
            return self._json_error("首次密码只能在本机设置", status=403)
        payload = await request.json()
        password = str(payload.get("password", ""))
        confirmation = str(payload.get("confirmation", ""))
        if password != confirmation:
            return self._json_error("两次输入的密码不一致", status=400)
        try:
            self.credentials.set_password(password)
        except ValueError as exc:
            return self._json_error(str(exc), status=400)
        token, session = self.sessions.create()
        response = web.json_response({"ok": True, "csrf_token": session.csrf_token})
        self._set_cookie(response, token)
        self.logger.info("控制台初始密码已从本机设置")
        return response

    async def _auth_login(self, request: web.Request) -> web.Response:
        if not self.credentials.configured:
            return self._json_error("请先从本机设置控制台密码", status=428)
        client = self._client_ip(request)
        retry_after = self.login_limiter.retry_after(client)
        if retry_after:
            response = self._json_error(
                f"登录尝试过多，请在 {retry_after} 秒后重试",
                status=429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
        payload = await request.json()
        password = str(payload.get("password", ""))
        verified = await asyncio.to_thread(self.credentials.verify, password)
        if not verified:
            self.login_limiter.record_failure(client)
            await asyncio.sleep(0.35)
            return self._json_error("密码错误", status=401)
        self.login_limiter.record_success(client)
        token, session = self.sessions.create()
        response = web.json_response({"ok": True, "csrf_token": session.csrf_token})
        self._set_cookie(response, token)
        return response

    async def _auth_logout(self, request: web.Request) -> web.Response:
        self.sessions.revoke(request.cookies.get(_COOKIE_NAME))
        response = web.json_response({"ok": True})
        response.del_cookie(_COOKIE_NAME, path="/")
        return response

    async def _change_password(self, request: web.Request) -> web.Response:
        payload = await request.json()
        current = str(payload.get("current_password", ""))
        new_password = str(payload.get("new_password", ""))
        confirmation = str(payload.get("confirmation", ""))
        if not await asyncio.to_thread(self.credentials.verify, current):
            return self._json_error("当前密码错误", status=401)
        if new_password != confirmation:
            return self._json_error("两次输入的新密码不一致", status=400)
        try:
            validate_password(new_password)
            await asyncio.to_thread(self.credentials.set_password, new_password)
        except ValueError as exc:
            return self._json_error(str(exc), status=400)
        self.sessions.revoke_all()
        return web.json_response({"ok": True, "login_required": True})

    async def _overview(self, request: web.Request) -> web.Response:
        disk = shutil.disk_usage(self.data_dir)
        app = self.application
        adapter = getattr(app, "adapter", None)
        queue_summary = self._queue_summary()
        return web.json_response(
            {
                "name": "NeoBot",
                "status": "running" if bool(getattr(app, "_started", False)) else "starting",
                "uptime_seconds": max(0, int(time.time() - self.started_at)),
                "started_at": datetime.fromtimestamp(self.started_at, UTC).isoformat(),
                "pid": os.getpid(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "adapter": {
                    "type": type(adapter).__name__ if adapter is not None else "unknown",
                    "connected": self._adapter_connected(adapter),
                    "mode": getattr(getattr(self.config, "adapter", None), "mode", "unknown"),
                },
                "queues": queue_summary,
                "tasks": len([task for task in asyncio.all_tasks() if not task.done()]),
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0,
                },
                "console": {
                    "role": request.app[_ROLE_KEY],
                    "public_enabled": bool(
                        getattr(getattr(self.config, "console", None), "enabled", False)
                    ),
                    "public_url": self.public_url,
                    "admin_url": self.admin_url
                    if request.app[_ROLE_KEY] == "admin"
                    else None,
                },
            }
        )

    async def _services(self, request: web.Request) -> web.Response:
        app = self.application
        services = {
            "NeoBot runtime": bool(getattr(app, "_started", False)),
            "Adapter": self._adapter_connected(getattr(app, "adapter", None)),
            "File server": bool(getattr(getattr(app, "file_server", None), "enabled", True)),
            "TTS": getattr(app, "tts_service", None) is not None,
            "Plugin runtime": getattr(app, "_plugin_runtime", None) is not None,
            "Emoji service": getattr(app, "_emoji_service", None) is not None,
            "Scheduled tasks": getattr(app, "_scheduled_task_manager", None) is not None,
            "Problem solver": getattr(app, "_problem_solver_manager", None) is not None,
            "Browser lifecycle": getattr(app, "_browser_lifecycle_manager", None) is not None,
            "Self heal": getattr(app, "_self_heal_manager", None) is not None,
        }
        if self.service_probe is not None:
            try:
                services.update(self.service_probe())
            except Exception:
                pass
        return web.json_response(
            {
                "services": [
                    {"name": name, "available": bool(value)}
                    for name, value in services.items()
                ]
            }
        )

    async def _tasks(self, request: web.Request) -> web.Response:
        current = asyncio.current_task()
        rows: list[dict[str, Any]] = []
        for task in asyncio.all_tasks():
            if task is current:
                continue
            coroutine = task.get_coro()
            rows.append(
                {
                    "name": task.get_name(),
                    "coroutine": getattr(coroutine, "__qualname__", type(coroutine).__name__),
                    "done": task.done(),
                    "cancelled": task.cancelled(),
                }
            )
        rows.sort(key=lambda row: (row["done"], row["name"]))
        return web.json_response({"tasks": rows[:500], "total": len(rows)})

    async def _logs(self, request: web.Request) -> web.Response:
        raw_limit = request.query.get("limit", "250")
        try:
            limit = max(20, min(2000, int(raw_limit)))
        except ValueError:
            limit = 250
        level = request.query.get("level", "").strip().upper()
        search = request.query.get("search", "").strip().casefold()[:100]
        lines = await asyncio.to_thread(self._read_log_tail, limit * 4)
        if level:
            lines = [line for line in lines if f"| {level}" in line.upper()]
        if search:
            lines = [line for line in lines if search in line.casefold()]
        return web.json_response({"lines": lines[-limit:], "count": min(limit, len(lines))})

    async def _log_stream(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache, no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)
        log_path = self.data_dir / "logs" / "neobot.log"
        position = log_path.stat().st_size if log_path.exists() else 0
        session_token = request.cookies.get(_COOKIE_NAME)
        try:
            while True:
                await asyncio.sleep(1)
                if self.sessions.get(session_token, touch=False) is None:
                    break
                if not log_path.exists():
                    await response.write(b": waiting\n\n")
                    continue
                size = log_path.stat().st_size
                if size < position:
                    position = 0
                if size == position:
                    await response.write(b": keepalive\n\n")
                    continue
                with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(position)
                    chunk = handle.read(64 * 1024)
                    position = handle.tell()
                for line in chunk.splitlines()[-200:]:
                    safe = redact(line)
                    payload = json.dumps({"line": safe}, ensure_ascii=False)
                    await response.write(f"data: {payload}\n\n".encode("utf-8"))
        except (asyncio.CancelledError, ConnectionError, RuntimeError):
            pass
        return response

    async def _debug_files(self, request: web.Request) -> web.Response:
        root = self.data_dir / "debug"
        files: list[dict[str, Any]] = []
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files.append(
                    {
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "size": stat.st_size,
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime, UTC
                        ).isoformat(),
                    }
                )
        files.sort(key=lambda item: item["modified_at"], reverse=True)
        return web.json_response({"files": files[:500], "total": len(files)})

    async def _diagnostics(self, request: web.Request) -> web.Response:
        return web.json_response(await self._build_diagnostics())

    async def _diagnostics_export(self, request: web.Request) -> web.Response:
        payload = await self._build_diagnostics()
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return web.Response(
            body=content,
            content_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="neobot-diagnostics-{stamp}.json"'
            },
        )

    async def _admin_config(self, request: web.Request) -> web.Response:
        serialized = self._serialize_dataclass(self.config._inner)
        root_fields = [
            item
            for item in serialized
            if item["kind"] != "section" and item["path"] != "version"
        ]
        sections = [item for item in serialized if item["kind"] == "section"]
        if root_fields:
            sections.insert(
                0,
                {
                    "path": "general",
                    "label": "general",
                    "description": "顶层配置",
                    "kind": "section",
                    "children": root_fields,
                },
            )
        return web.json_response(
            {
                "sections": sections,
                "restart_note": "大部分配置保存后需要重启 NeoBot 才会完全生效。",
            }
        )

    async def _admin_update_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        updates = payload.get("updates")
        if not isinstance(updates, list) or not updates:
            return self._json_error("updates 必须是非空数组", status=400)
        if len(updates) > 100:
            return self._json_error("单次最多更新 100 个配置项", status=400)
        async with self._config_lock:
            try:
                document = tomlkit.parse(CONFIG_FILE.read_text(encoding="utf-8"))
                changed: list[str] = []
                for update in updates:
                    if not isinstance(update, dict):
                        raise ValueError("配置更新项格式错误")
                    path = str(update.get("path", "")).strip()
                    if path == "version" or not path:
                        raise ValueError(f"不允许更新配置路径: {path or '(empty)'}")
                    self._set_document_value(document, path, update.get("value"))
                    changed.append(path)
                raw_config = document.unwrap()
                raw_console = raw_config.get("console", {})
                if not isinstance(raw_console, dict):
                    raise TypeError("console 必须是配置表")
                Console(**raw_console)
                validated = dict_to_dataclass(raw_config, BotConfig)
                rendered = tomlkit.dumps(document)
            except (ValueError, TypeError, KeyError, tomlkit.exceptions.ParseError) as exc:
                return self._json_error(f"配置校验失败: {exc}", status=400)
            await asyncio.to_thread(backup_config, CONFIG_FILE, CONFIG_BACKUP_DIR)
            await asyncio.to_thread(self._atomic_write, CONFIG_FILE, rendered)
            self.config.reload(validated)
        self.logger.info("管理员控制台已保存配置", fields=", ".join(changed))
        return web.json_response(
            {
                "ok": True,
                "changed": changed,
                "restart_required": True,
            }
        )

    async def _admin_environment(self, request: web.Request) -> web.Response:
        records = self._read_environment()
        return web.json_response(
            {
                "variables": [
                    {
                        "key": key,
                        "configured": bool(value),
                        "sensitive": bool(_SENSITIVE_ENV_PATTERN.search(key)),
                        "preview": self._environment_preview(key, value),
                    }
                    for key, value in sorted(records.items(), key=lambda pair: pair[0].casefold())
                ],
                "note": "密钥值不会通过接口返回；留空不会覆盖现有值。",
            }
        )

    async def _admin_update_environment(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        if not _ENV_KEY_PATTERN.fullmatch(key):
            return self._json_error("环境变量名格式无效", status=400)
        payload = await request.json()
        value = payload.get("value")
        if not isinstance(value, str) or not value:
            return self._json_error("值不能为空；如需移除请使用删除操作", status=400)
        if len(value) > 16384 or "\n" in value or "\r" in value:
            return self._json_error("环境变量值格式无效", status=400)
        async with self._config_lock:
            await asyncio.to_thread(self._write_environment_value, key, value)
            os.environ[key] = value
        self.logger.info("管理员控制台已更新环境变量", key=key)
        return web.json_response({"ok": True, "key": key, "restart_required": True})

    async def _admin_delete_environment(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        if not _ENV_KEY_PATTERN.fullmatch(key):
            return self._json_error("环境变量名格式无效", status=400)
        async with self._config_lock:
            await asyncio.to_thread(self._delete_environment_value, key)
            os.environ.pop(key, None)
        self.logger.info("管理员控制台已移除环境变量", key=key)
        return web.json_response({"ok": True, "key": key, "restart_required": True})

    async def _build_diagnostics(self) -> dict[str, Any]:
        log_lines = await asyncio.to_thread(self._read_log_tail, 120)
        error_lines = [
            line
            for line in log_lines
            if "| ERROR" in line.upper() or "| CRITICAL" in line.upper()
        ]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "runtime": {
                "status": "running"
                if bool(getattr(self.application, "_started", False))
                else "starting",
                "uptime_seconds": max(0, int(time.time() - self.started_at)),
                "pid": os.getpid(),
                "python": sys.version,
                "platform": platform.platform(),
                "executable": Path(sys.executable).name,
            },
            "queues": self._queue_summary(),
            "paths": {
                "data_dir_exists": self.data_dir.exists(),
                "config_exists": CONFIG_FILE.exists(),
                "environment_exists": ENV_FILE.exists(),
                "database_exists": (self.data_dir / "neobot.db").exists(),
                "log_exists": (self.data_dir / "logs" / "neobot.log").exists(),
            },
            "configuration": redact(self._safe_config_summary()),
            "recent_errors": [redact(line) for line in error_lines[-30:]],
        }

    def _queue_summary(self) -> dict[str, Any]:
        def summarize(queue: Any) -> dict[str, int]:
            queues = getattr(queue, "_queues", {}) if queue is not None else {}
            return {
                "conversations": len(queues),
                "entries": sum(len(items) for items in queues.values()),
            }

        return {
            "group": summarize(self.group_queue),
            "friend": summarize(self.friend_queue),
        }

    def _safe_config_summary(self) -> dict[str, Any]:
        config = self.config
        return {
            "version": getattr(config, "version", None),
            "bot": {
                "account": getattr(getattr(config, "bot", None), "account", None),
                "nick_name": getattr(getattr(config, "bot", None), "nick_name", None),
            },
            "adapter": {
                "mode": getattr(getattr(config, "adapter", None), "mode", None),
            },
            "debug": {
                "enabled": bool(getattr(getattr(config, "debug", None), "enabled", False)),
            },
            "console": {
                "enabled": bool(
                    getattr(getattr(config, "console", None), "enabled", False)
                ),
                "admin_enabled": bool(
                    getattr(getattr(config, "console", None), "admin_enabled", False)
                ),
            },
        }

    def _serialize_dataclass(self, value: Any, path: str = "") -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not is_dataclass(value):
            return result
        for descriptor in fields(value):
            item = getattr(value, descriptor.name)
            item_path = f"{path}.{descriptor.name}" if path else descriptor.name
            description = str(descriptor.metadata.get("description", ""))
            if is_dataclass(item):
                result.append(
                    {
                        "path": item_path,
                        "label": descriptor.name,
                        "description": description,
                        "kind": "section",
                        "children": self._serialize_dataclass(item, item_path),
                    }
                )
                continue
            sensitive = bool(_SENSITIVE_ENV_PATTERN.search(descriptor.name))
            result.append(
                {
                    "path": item_path,
                    "label": descriptor.name,
                    "description": description,
                    "kind": self._value_kind(item),
                    "value": mask_secret(item) if sensitive else item,
                    "sensitive": sensitive,
                    "editable": not sensitive,
                }
            )
        return result

    @staticmethod
    def _value_kind(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "mapping"
        if value is None:
            return "null"
        return "string"

    @staticmethod
    def _set_document_value(document: Any, path: str, value: Any) -> None:
        segments = path.split(".")
        if not all(_ENV_KEY_PATTERN.fullmatch(segment) for segment in segments):
            raise ValueError(f"配置路径格式无效: {path}")
        target = document
        for segment in segments[:-1]:
            if segment not in target or not hasattr(target[segment], "__getitem__"):
                raise KeyError(f"配置路径不存在: {path}")
            target = target[segment]
        leaf = segments[-1]
        if leaf not in target:
            raise KeyError(f"配置路径不存在: {path}")
        current = target[leaf]
        current_value = current.unwrap() if hasattr(current, "unwrap") else current
        if isinstance(current_value, bool) and not isinstance(value, bool):
            raise TypeError(f"{path} 必须是布尔值")
        if isinstance(current_value, int) and not isinstance(current_value, bool):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{path} 必须是整数")
        if isinstance(current_value, float) and not isinstance(value, (int, float)):
            raise TypeError(f"{path} 必须是数字")
        if isinstance(current_value, list) and not isinstance(value, list):
            raise TypeError(f"{path} 必须是数组")
        if isinstance(current_value, dict) and not isinstance(value, dict):
            raise TypeError(f"{path} 必须是对象")
        target[leaf] = value

    def _read_log_tail(self, limit: int) -> list[str]:
        path = self.data_dir / "logs" / "neobot.log"
        if not path.exists():
            return []
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - 1024 * 1024))
            content = handle.read().decode("utf-8", errors="replace")
        return [str(redact(line)) for line in content.splitlines()[-limit:]]

    @staticmethod
    def _adapter_connected(adapter: Any) -> bool:
        if adapter is None:
            return False
        for name in ("connected", "is_connected"):
            value = getattr(adapter, name, None)
            if isinstance(value, bool):
                return value
            if callable(value):
                try:
                    return bool(value())
                except Exception:
                    pass
        if not getattr(adapter, "requires_connection_wait", True):
            return True
        return bool(getattr(adapter, "_started", False))

    def _client_ip(self, request: web.Request) -> str:
        settings = getattr(self.config, "console", None)
        if bool(getattr(settings, "trust_proxy_headers", False)):
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        peername = request.transport.get_extra_info("peername") if request.transport else None
        if isinstance(peername, tuple) and peername:
            return str(peername[0])
        return request.remote or ""

    def _set_cookie(self, response: web.StreamResponse, token: str) -> None:
        settings = getattr(self.config, "console", None)
        response.set_cookie(
            _COOKIE_NAME,
            token,
            max_age=self.sessions.timeout_seconds,
            httponly=True,
            secure=bool(getattr(settings, "secure_cookies", False)),
            samesite="Strict",
            path="/",
        )

    async def _prepare_headers(
        self,
        request: web.Request,
        response: web.StreamResponse,
    ) -> None:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"

    @staticmethod
    def _json_error(message: str, *, status: int) -> web.Response:
        return web.json_response({"ok": False, "error": message}, status=status)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".console.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _read_environment() -> dict[str, str]:
        records: dict[str, str] = {}
        if not ENV_FILE.exists():
            return records
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            records[key.strip()] = value
        return records

    @staticmethod
    def _environment_preview(key: str, value: str) -> str:
        if key.upper().endswith("_URL") and not _SENSITIVE_ENV_PATTERN.search(key):
            return value
        return mask_secret(value)

    @staticmethod
    def _write_environment_value(key: str, value: str) -> None:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
        target = key.casefold()
        found = False
        output: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                existing_key = stripped.split("=", 1)[0].strip()
                if existing_key.casefold() == target:
                    output.append(f"{existing_key}={value}")
                    found = True
                    continue
            output.append(line)
        if not found:
            if output and output[-1]:
                output.append("")
            output.append(f"{key}={value}")
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ConsoleService._atomic_write(ENV_FILE, "\n".join(output) + "\n")

    @staticmethod
    def _delete_environment_value(key: str) -> None:
        if not ENV_FILE.exists():
            return
        target = key.casefold()
        output: list[str] = []
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                existing_key = stripped.split("=", 1)[0].strip()
                if existing_key.casefold() == target:
                    continue
            output.append(line)
        ConsoleService._atomic_write(ENV_FILE, "\n".join(output) + "\n")


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
