"""网页面板 HTTP 服务：路由、鉴权中间件与静态资源。

与旧内置控制台不同，本面板是官方插件，配置直接读取 config.toml 的 [dashboard]，
默认监听 0.0.0.0:9981（对网络开放），可通过 host/port/base_path 调整。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from neobot_app.panel_auth import get_panel_password_store

from . import system as system_module
from .api import DashboardApi, _json_error
from .config import DashboardConfig
from .config_manager import BotConfigManager, EnvFileManager
from .metrics import Metrics
from .security import (
    LoginLimiter,
    SessionStore,
    client_ip,
    is_loopback,
    secrets_equal,
)

COOKIE_NAME = "neobot_dashboard_session"
_STATIC_DIR = Path(__file__).resolve().parent / "web"
_INDEX_FILE = _STATIC_DIR / "index.html"
_API_PREFIX = "/api/"
_PORT_SEARCH_LIMIT = 10


class DashboardServer:
    """面板服务主体。"""

    version = "1.0.0"

    def __init__(
        self,
        *,
        plugin_name: str,
        config: DashboardConfig,
        data_dir: Path,
        logger: Any,
        adapter: Any = None,
        plugin_control: Any = None,
        services: Any = None,
        config_path: Path,
        env_path: Path,
        backup_dir: Path,
        host_commands: Any = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.config = config
        self.data_dir = Path(data_dir)
        self.logger = logger
        self.adapter = adapter
        self.plugin_control = plugin_control
        self.services = services
        self.host_commands = host_commands

        self.base_path = config.prefix
        self._manage_plugins = bool(config.manage_plugins)
        self._allow_remote_manage = bool(config.allow_remote_manage)
        self.secure_cookies = bool(config.secure_cookies)
        self.trust_proxy = bool(config.trust_proxy_headers)

        self.sessions = SessionStore(timeout_seconds=config.session_timeout_minutes * 60)
        self.limiter = LoginLimiter(
            max_failures=config.login_max_failures,
            window_seconds=float(config.login_rate_limit_window_seconds),
        )
        self.passwords = get_panel_password_store(self.data_dir / "auth.json")

        self.metrics = Metrics(
            data_dir=self.data_dir,
            history_max_days=config.history_max_days,
            log_buffer_size=config.log_buffer_size,
            logger=logger,
        )
        self.config_manager = BotConfigManager(
            config_path=config_path, backup_dir=backup_dir, logger=logger
        )
        self.env_manager = EnvFileManager(
            env_path=env_path, backup_dir=backup_dir, logger=logger
        )
        self.api = DashboardApi(console=self)

        self._started_at = time.time()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._bot_cache: dict[str, Any] = {}
        self._bot_cache_at = 0.0
        self._bot_lock = asyncio.Lock()
        self.public_url: str | None = None
        self.bound_port: int | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @property
    def uptime_seconds(self) -> int:
        return int(max(0.0, time.time() - self._started_at))

    def _live_section(self) -> Any:
        """读取本体内存中的 [dashboard] 配置，使管理开关在重载后立即生效。"""
        services = self.services
        getter = getattr(services, "get", None) if services is not None else None
        if not callable(getter):
            return None
        try:
            proxy = getter("config")
        except Exception:
            return None
        section = getattr(proxy, "dashboard", None) if proxy is not None else None
        return section

    @property
    def manage_plugins(self) -> bool:
        section = self._live_section()
        if section is not None:
            return bool(getattr(section, "manage_plugins", self._manage_plugins))
        return self._manage_plugins

    @property
    def allow_remote_manage(self) -> bool:
        section = self._live_section()
        if section is not None:
            return bool(getattr(section, "allow_remote_manage", self._allow_remote_manage))
        return self._allow_remote_manage

    async def start(self) -> str | None:
        app = self._make_app()
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=5)
        await runner.setup()
        last_error: OSError | None = None
        port = self.config.port
        for offset in range(_PORT_SEARCH_LIMIT):
            candidate = self.config.port + offset
            if candidate > 65535:
                break
            site = web.TCPSite(runner, host=self.config.host, port=candidate)
            try:
                await site.start()
            except OSError as exc:
                last_error = exc
                continue
            port = candidate
            break
        else:
            await runner.cleanup()
            raise OSError(
                f"面板端口从 {self.config.port} 起的 {_PORT_SEARCH_LIMIT} 个端口均不可用: {last_error}"
            )
        self._runner = runner
        self._site = site
        self.bound_port = port
        display_host = "<服务器IP>" if self.config.host in {"0.0.0.0", "::"} else self.config.host
        prefix = self.base_path or ""
        self.public_url = f"http://{display_host}:{port}{prefix}/"
        if port != self.config.port:
            self.logger.warning(
                f"面板端口 {self.config.port} 被占用，已改用 {port}；请同步修改 dashboard.port"
            )
        self.logger.info(
            "网页面板已启动",
            url=self.public_url,
            local_url=f"http://127.0.0.1:{port}{prefix}/",
            listen_host=self.config.host,
            password_configured=self.passwords.configured,
        )
        if not self.passwords.configured:
            self.logger.warning(
                "网页面板尚未设置登录密码：此时不允许外网访问。"
                "请在本机打开面板按提示设置密码，或由超级管理员在 QQ 私聊发送 /set_password 设置"
            )
        return self.public_url

    async def stop(self) -> None:
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception as exc:
                self.logger.warning(f"网页面板关闭失败: {exc}")
        self._runner = None
        self._site = None
        self.public_url = None
        self.metrics.flush()

    # ------------------------------------------------------------------
    # 应用装配
    # ------------------------------------------------------------------

    def _make_app(self) -> web.Application:
        app = web.Application(
            middlewares=[self._error_middleware, self._auth_middleware],
            client_max_size=2 * 1024 * 1024,
        )
        app.on_response_prepare.append(self._security_headers)

        self._route(app, "GET", "/healthz", self._healthz)
        self._route(app, "GET", "/api/auth/status", self.api.auth_status)
        self._route(app, "POST", "/api/auth/setup", self.api.auth_setup)
        self._route(app, "POST", "/api/auth/login", self.api.auth_login)
        self._route(app, "POST", "/api/auth/logout", self.api.auth_logout)
        self._route(app, "GET", "/api/auth/me", self.api.auth_me)

        self._route(app, "GET", "/api/overview", self.api.overview)
        self._route(app, "GET", "/api/system", self.api.system)
        self._route(app, "GET", "/api/bots", self.api.bots)
        self._route(app, "GET", "/api/bot/detail", self.api.bot_detail)
        self._route(app, "GET", "/api/series/messages", self.api.series_messages)
        self._route(app, "GET", "/api/series/latency", self.api.series_latency)
        self._route(app, "GET", "/api/stats/api-calls", self.api.stats_api_calls)
        self._route(app, "GET", "/api/stats/active-users", self.api.stats_active_users)
        self._route(app, "GET", "/api/stats/usage", self.api.stats_usage)
        self._route(app, "GET", "/api/series/usage", self.api.series_usage)
        self._route(app, "GET", "/api/logs", self.api.logs)
        self._route(app, "GET", "/api/tasks", self.api.tasks)
        self._route(app, "GET", "/api/services", self.api.services)

        self._route(app, "GET", "/api/plugins", self.api.plugins)
        self._route(app, "POST", "/api/plugins/install", self.api.plugins_install)
        self._route(app, "POST", "/api/plugins/proxy", self.api.plugins_proxy_save)
        self._route(app, "GET", "/api/plugins/check-updates", self.api.plugins_check_updates)
        self._route(app, "POST", "/api/plugins/{name}/toggle", self.api.plugin_toggle)
        self._route(app, "POST", "/api/plugins/{name}/reload", self.api.plugin_reload)
        self._route(app, "POST", "/api/plugins/{name}/update", self.api.plugin_update)
        self._route(app, "POST", "/api/plugins/{name}/uninstall", self.api.plugin_uninstall)
        self._route(app, "GET", "/api/plugins/{name}/config", self.api.plugin_config_get)
        self._route(app, "POST", "/api/plugins/{name}/config", self.api.plugin_config_save)

        self._route(app, "GET", "/api/config", self.api.config_get)
        self._route(app, "POST", "/api/config", self.api.config_save)
        self._route(app, "POST", "/api/config/validate", self.api.config_validate)
        self._route(app, "POST", "/api/config/reload", self.api.config_reload)
        self._route(app, "GET", "/api/config/models", self.api.config_models)
        self._route(app, "POST", "/api/config/models/library", self.api.models_library_save)
        self._route(app, "POST", "/api/config/models/assignments", self.api.models_assignments_save)
        self._route(app, "GET", "/api/config/env", self.api.env_get)
        self._route(app, "POST", "/api/config/env", self.api.env_save)
        self._route(app, "POST", "/api/config/env/platform", self.api.env_platform_add)
        self._route(app, "POST", "/api/admin/restart", self.api.admin_restart)

        self._route(app, "GET", "/favicon.ico", self._favicon)
        self._route(app, "GET", "/image/{name}", self._image)
        self._route(app, "GET", "/assets/{name}", self._asset)
        self._route(app, "GET", "/", self._index)
        self._route(app, "GET", "/{tail:.*}", self._spa_fallback)
        return app

    def _route(self, app: web.Application, method: str, path: str, handler: Any) -> None:
        app.router.add_route(method, path, handler)
        if self.base_path:
            prefixed = f"{self.base_path}{path}" if path != "/" else f"{self.base_path}/"
            app.router.add_route(method, prefixed, handler)

    # ------------------------------------------------------------------
    # 中间件
    # ------------------------------------------------------------------

    @web.middleware
    async def _error_middleware(self, request: web.Request, handler: Any) -> web.StreamResponse:
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        except Exception as exc:
            self.logger.exception(f"面板请求处理失败 path={request.path}: {exc}")
            return _json_error("服务器处理请求失败", status=500)

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler: Any) -> web.StreamResponse:
        path = self._strip_base(request.path)
        ip = self.request_ip(request)
        loopback = is_loopback(ip)
        configured = self.passwords.configured

        if not configured:
            # 未设置密码：禁止外网访问；本机只允许进入设置流程。
            # 状态接口与静态资源始终可访问，便于前端展示明确的提示。
            if path == "/api/auth/status" or not path.startswith(_API_PREFIX):
                return await handler(request)
            if not loopback:
                return _json_error(
                    "面板尚未设置登录密码，已禁止外网访问。"
                    "请在本机打开面板设置密码，或由超级管理员在 QQ 私聊发送 /set_password 设置",
                    status=403,
                    setup_required=True,
                    loopback=False,
                )
            if path == "/api/auth/setup":
                return await handler(request)
            return _json_error(
                "面板尚未设置登录密码，请先在本机完成设置",
                status=403,
                setup_required=True,
                loopback=True,
            )

        public = {
            "/healthz",
            "/",
            "/favicon.ico",
            "/api/auth/status",
            "/api/auth/login",
            # 已配置密码时由处理器直接返回「请直接登录」，避免暴露为需登录接口
            "/api/auth/setup",
        }
        if not path.startswith(_API_PREFIX) and path not in public and not path.startswith("/assets/") and not path.startswith("/image/"):
            # 静态资源与 SPA 页面本身不需要鉴权（数据全部来自 /api）
            return await handler(request)
        if path in public or path.startswith("/assets/") or path.startswith("/image/"):
            return await handler(request)

        token = request.headers.get("X-Token") or request.cookies.get(COOKIE_NAME) or ""
        session = self.sessions.get(
            token, password_revision=self.passwords.revision
        )
        if session is None:
            return _json_error("需要登录", status=401)
        request["dashboard_session"] = session
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not supplied or not secrets_equal(supplied, session.csrf_token):
                return _json_error("CSRF 校验失败，请刷新页面后重试", status=403)
        return await handler(request)

    async def _security_headers(self, request: web.Request, response: web.StreamResponse) -> None:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'"
        )
        if self._strip_base(request.path).startswith(_API_PREFIX):
            response.headers["Cache-Control"] = "no-store"

    def _strip_base(self, path: str) -> str:
        if self.base_path and path.startswith(self.base_path):
            stripped = path[len(self.base_path) :]
            return stripped or "/"
        return path

    # ------------------------------------------------------------------
    # 静态资源
    # ------------------------------------------------------------------

    async def _index(self, request: web.Request) -> web.StreamResponse:
        if not _INDEX_FILE.is_file():
            return web.Response(
                text=(
                    "网页面板前端资源缺失。\n"
                    f"请在 {_STATIC_DIR.parent / 'frontend'} 目录执行 npm install && npm run build 生成 web/ 产物。"
                ),
                content_type="text/plain",
                status=503,
            )
        return web.FileResponse(_INDEX_FILE, headers={"Cache-Control": "no-store"})

    async def _spa_fallback(self, request: web.Request) -> web.StreamResponse:
        path = self._strip_base(request.path)
        if path.startswith(_API_PREFIX):
            return _json_error("接口不存在", status=404)
        return await self._index(request)

    async def _asset(self, request: web.Request) -> web.StreamResponse:
        return self._static_file("assets", request.match_info.get("name", ""))

    async def _image(self, request: web.Request) -> web.StreamResponse:
        return self._static_file("image", request.match_info.get("name", ""))

    async def _favicon(self, request: web.Request) -> web.StreamResponse:
        icon = _STATIC_DIR / "image" / "icon.webp"
        if icon.is_file():
            return web.FileResponse(icon, headers={"Cache-Control": "public, max-age=86400"})
        return web.Response(status=404)

    def _static_file(self, folder: str, name: str) -> web.StreamResponse:
        candidate = (Path(folder) / name).as_posix()
        if ".." in Path(candidate).parts or not candidate:
            return web.Response(status=404)
        target = (_STATIC_DIR / candidate).resolve()
        try:
            target.relative_to(_STATIC_DIR.resolve())
        except ValueError:
            return web.Response(status=404)
        if not target.is_file():
            return web.Response(status=404)
        return web.FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})

    async def _healthz(self, request: web.Request) -> web.StreamResponse:
        return web.json_response(
            {
                "ok": True,
                "uptime_seconds": self.uptime_seconds,
                "version": self.version,
                "plugin": self.plugin_name,
            }
        )

    # ------------------------------------------------------------------
    # 会话 / 令牌 / 机器人信息
    # ------------------------------------------------------------------

    def verify_password(self, supplied: str) -> bool:
        """校验面板密码（恒定时间比较，由 PanelPasswordStore 负责）。"""
        return self.passwords.verify(supplied)

    def create_session(self, request: web.Request) -> Any:
        """登录成功后创建会话（绑定当前密码版本）。"""
        return self.sessions.create(
            ip=self.request_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
            password_revision=self.passwords.revision,
        )

    def request_ip(self, request: web.Request) -> str:
        return client_ip(request, trust_proxy=self.trust_proxy)

    def set_session_cookie(self, response: web.StreamResponse, token: str) -> None:
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=self.secure_cookies,
            samesite="Lax",
            path=self.base_path or "/",
            max_age=int(self.sessions.timeout_seconds),
        )

    def clear_session_cookie(self, response: web.StreamResponse) -> None:
        response.del_cookie(COOKIE_NAME, path=self.base_path or "/")

    async def bot_info(self) -> dict[str, Any]:
        """获取机器人信息（带缓存）。"""
        ttl = float(self.config.bot_info_cache_ttl)
        now = time.time()
        if ttl > 0 and self._bot_cache and now - self._bot_cache_at < ttl:
            return self._bot_cache
        async with self._bot_lock:
            if ttl > 0 and self._bot_cache and time.time() - self._bot_cache_at < ttl:
                return self._bot_cache
            info = await self._probe_bot()
            self._bot_cache = info
            self._bot_cache_at = time.time()
            return info

    async def _probe_bot(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "online": False,
            "user_id": None,
            "nickname": "",
            "app_name": "",
            "app_version": "",
            "avatar_url": "",
        }
        adapter = self.adapter
        if adapter is None:
            return info
        info["online"] = bool(getattr(adapter, "connected", False))
        call_api = getattr(adapter, "call_api", None)
        if not callable(call_api):
            return info
        try:
            payload = await asyncio.wait_for(call_api("get_login_info", {}, 5.0), timeout=8.0)
        except Exception:
            payload = None
        data = _unwrap(payload)
        if data:
            info["online"] = True
            info["user_id"] = data.get("user_id")
            info["nickname"] = str(data.get("nickname") or "")
        try:
            payload = await asyncio.wait_for(call_api("get_version_info", {}, 5.0), timeout=8.0)
        except Exception:
            payload = None
        data = _unwrap(payload)
        if data:
            info["app_name"] = str(data.get("app_name") or "")
            info["app_version"] = str(data.get("app_version") or "")
        if info["user_id"]:
            info["avatar_url"] = f"https://q1.qlogo.cn/g?b=qq&nk={info['user_id']}&s=640"
        return info

    async def probe_latency(self) -> float | None:
        """测量一次 API 往返延迟并写入指标。"""
        adapter = self.adapter
        call_api = getattr(adapter, "call_api", None) if adapter is not None else None
        if not callable(call_api):
            return None
        started = time.perf_counter()
        ok = False
        try:
            payload = await asyncio.wait_for(call_api("get_status", {}, 5.0), timeout=8.0)
            ok = payload is not None
        except Exception:
            ok = False
        elapsed = (time.perf_counter() - started) * 1000.0
        self.metrics.record_latency(elapsed if ok else None, ok=ok)
        return elapsed if ok else None

    def describe(self) -> dict[str, Any]:
        """面板自身状态（供诊断接口使用）。"""
        return {
            "url": self.public_url,
            "host": self.config.host,
            "port": self.bound_port or self.config.port,
            "base_path": self.base_path,
            "password_configured": self.passwords.configured,
            "manage_plugins": self.manage_plugins,
            "allow_remote_manage": self.allow_remote_manage,
            "loopback_only": is_loopback(self.config.host),
            "sessions": self.sessions.describe(),
            "system": system_module.snapshot(data_dir=self.data_dir),
        }


def _unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload
