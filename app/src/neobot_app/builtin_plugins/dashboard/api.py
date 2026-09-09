"""网页面板 HTTP 接口实现。

所有写操作都经过 _require_manage 校验（manage_plugins / allow_remote_manage），
所有响应都只暴露必要信息，密钥类字段默认打码。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from . import system as system_module
from .config_manager import (
    BotConfigManager,
    ConfigConflictError,
    ConfigValidationError,
    EnvFileManager,
    models_view,
)
from .plugin_config import PluginConfigConflictError, PluginConfigEditor, PluginConfigError
from .security import client_ip, is_loopback


def _json_ok(data: Any = None, **extra: Any) -> web.Response:
    payload: dict[str, Any] = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    payload.update(extra)
    return web.json_response(payload)


def _json_error(message: str, *, status: int = 400, **extra: Any) -> web.Response:
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return web.json_response(payload, status=status)


class DashboardApi:
    """面板接口集合。"""

    def __init__(self, *, console: Any) -> None:
        self.console = console

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------

    @property
    def logger(self) -> Any:
        return self.console.logger

    @property
    def metrics(self) -> Any:
        return self.console.metrics

    def _service(self, name: str, default: Any = None) -> Any:
        services = self.console.services
        if services is None:
            return default
        getter = getattr(services, "get", None)
        if not callable(getter):
            return default
        try:
            value = getter(name, default)
        except Exception:
            return default
        return default if value is None else value

    def _config_proxy(self) -> Any:
        return self._service("config")

    def _plugin_control(self) -> Any:
        control = self.console.plugin_control
        if control is None:
            control = self._service("plugin_runtime")
            control = getattr(control, "control", None)
        return control

    def _require_manage(self, request: web.Request, *, action: str = "管理操作") -> web.Response | None:
        if not self.console.manage_plugins:
            return _json_error("面板已禁用管理功能（dashboard.manage_plugins=false）", status=403)
        if not self.console.allow_remote_manage and not is_loopback(self.console.request_ip(request)):
            return _json_error(
                "远程管理已关闭（dashboard.allow_remote_manage=false），请在本机操作",
                status=403,
            )
        return None

    async def _read_json(self, request: web.Request) -> dict[str, Any]:
        if not request.can_read_body:
            return {}
        try:
            payload = await request.json()
        except Exception as exc:
            raise ValueError(f"请求体不是有效 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    async def auth_status(self, request: web.Request) -> web.Response:
        return _json_ok(
            {
                "authenticated": False,
                "loopback": is_loopback(self.console.request_ip(request)),
                "can_manage": self.console.manage_plugins
                and (
                    self.console.allow_remote_manage
                    or is_loopback(self.console.request_ip(request))
                ),
                "base_path": self.console.base_path,
                "version": self.console.version,
            }
        )

    async def auth_me(self, request: web.Request) -> web.Response:
        session = request.get("dashboard_session")
        ip = self.console.request_ip(request)
        return _json_ok(
            {
                "authenticated": True,
                "session": session.to_payload(timeout_seconds=self.console.sessions.timeout_seconds)
                if session is not None
                else {},
                "csrf_token": session.csrf_token if session is not None else "",
                "loopback": is_loopback(ip),
                "can_manage": self.console.manage_plugins
                and (self.console.allow_remote_manage or is_loopback(ip)),
                "manage_plugins": self.console.manage_plugins,
                "allow_remote_manage": self.console.allow_remote_manage,
                "base_path": self.console.base_path,
                "version": self.console.version,
            }
        )

    async def auth_login(self, request: web.Request) -> web.Response:
        ip = self.console.request_ip(request)
        locked, remaining = self.console.limiter.is_locked(ip)
        if locked:
            return _json_error(
                f"登录失败次数过多，请在 {remaining} 秒后重试", status=429
            )
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        supplied = str(payload.get("access_token") or payload.get("token") or "")
        if not self.console.verify_token(supplied):
            self.console.limiter.record_failure(ip)
            self.logger.warning(f"面板登录失败 ip={ip}")
            return _json_error("访问令牌不正确", status=401)
        self.console.limiter.reset(ip)
        session = self.console.sessions.create(
            ip=ip, user_agent=request.headers.get("User-Agent", "")
        )
        response = _json_ok(
            {
                "token": session.token,
                "csrf_token": session.csrf_token,
                "session": session.to_payload(
                    timeout_seconds=self.console.sessions.timeout_seconds
                ),
            }
        )
        self.console.set_session_cookie(response, session.token)
        self.logger.info(f"面板登录成功 ip={ip}")
        return response

    async def auth_logout(self, request: web.Request) -> web.Response:
        session = request.get("dashboard_session")
        if session is not None:
            self.console.sessions.revoke(session.token)
        response = _json_ok({"message": "已退出登录"})
        self.console.clear_session_cookie(response)
        return response

    # ------------------------------------------------------------------
    # 概览 / 系统 / 机器人
    # ------------------------------------------------------------------

    async def overview(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        stats = self.metrics.message_stats()
        system = system_module.snapshot(data_dir=self.console.data_dir)
        plugins = self._plugin_summary()
        return _json_ok(
            {
                "online": bool(bot.get("online")),
                "app_name": bot.get("app_name") or "",
                "app_version": bot.get("app_version") or "",
                "bot_nickname": bot.get("nickname") or "",
                "bot_user_id": bot.get("user_id"),
                "avatar_url": bot.get("avatar_url") or "",
                "uptime_seconds": self.console.uptime_seconds,
                "today_messages": stats["today"],
                "total_messages": stats["total"],
                "plugins_loaded": plugins["loaded"],
                "plugins_total": plugins["total"],
                "plugins_error": plugins["error"],
                "latency_ms": self.metrics.latency_series()["current_ms"],
                "python_version": system.get("python_version"),
                "hostname": system.get("hostname"),
            }
        )

    async def system(self, request: web.Request) -> web.Response:
        payload = system_module.snapshot(data_dir=self.console.data_dir)
        payload["uptime_seconds"] = self.console.uptime_seconds
        return _json_ok(payload)

    async def bots(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        latency = self.metrics.latency_series()
        return web.json_response(
            [
                {
                    "name": bot.get("nickname") or "未连接",
                    "user_id": bot.get("user_id"),
                    "platform": bot.get("app_name") or "OneBot",
                    "status": "on" if bot.get("online") else "off",
                    "latency_ms": latency.get("current_ms"),
                    "avatar_initial": (str(bot.get("nickname") or "N")[:1] or "N"),
                    "avatar_url": bot.get("avatar_url") or "",
                }
            ]
        )

    async def bot_detail(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        stats = self.metrics.message_stats()
        latency = self.metrics.latency_series()
        return _json_ok(
            {
                "nickname": bot.get("nickname") or "",
                "user_id": bot.get("user_id"),
                "avatar_url": bot.get("avatar_url") or "",
                "online": bool(bot.get("online")),
                "app_name": bot.get("app_name") or "",
                "app_version": bot.get("app_version") or "",
                "latency_ms": latency.get("current_ms"),
                "uptime_seconds": self.console.uptime_seconds,
                "today_messages": stats["today"],
                "total_messages": stats["total"],
            }
        )

    async def series_messages(self, request: web.Request) -> web.Response:
        days = self._int_arg(request, "days", 30, minimum=1, maximum=365)
        return _json_ok({"series": self.metrics.message_series(days), "days": days})

    async def series_latency(self, request: web.Request) -> web.Response:
        return _json_ok(self.metrics.latency_series())

    async def stats_api_calls(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 10, minimum=1, maximum=100)
        return _json_ok(self.metrics.api_calls(limit))

    async def stats_active_users(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 10, minimum=1, maximum=100)
        return _json_ok(self.metrics.active_users(limit))

    async def stats_usage(self, request: web.Request) -> web.Response:
        hours = self._int_arg(request, "hours", 24, minimum=1, maximum=24 * 365)
        session_factory = self._service("usage_session_factory")
        if session_factory is None:
            return _json_ok({"available": False, "items": [], "totals": {}})
        try:
            from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

            import datetime as _dt

            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                records = await repo.stats_since(cutoff)
        except Exception as exc:
            self.logger.warning(f"读取模型用量失败: {exc}")
            return _json_ok({"available": False, "items": [], "totals": {}, "error": str(exc)})
        by_module: dict[str, dict[str, float]] = {}
        totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
        for record in records:
            group = by_module.setdefault(
                str(record.module_name), {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
            )
            group["calls"] += 1
            group["input_tokens"] += int(record.input_tokens or 0)
            group["output_tokens"] += int(record.output_tokens or 0)
            group["cost_cny"] += float(record.cost_cny or 0.0)
            totals["calls"] += 1
            totals["input_tokens"] += int(record.input_tokens or 0)
            totals["output_tokens"] += int(record.output_tokens or 0)
            totals["cost_cny"] += float(record.cost_cny or 0.0)
        items = [
            {"module": module, **values}
            for module, values in sorted(
                by_module.items(), key=lambda item: item[1]["cost_cny"], reverse=True
            )
        ]
        totals["cost_cny"] = round(totals["cost_cny"], 6)
        return _json_ok({"available": True, "hours": hours, "totals": totals, "items": items})

    # ------------------------------------------------------------------
    # 日志 / 任务 / 服务
    # ------------------------------------------------------------------

    async def logs(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 200, minimum=1, maximum=2000)
        since = self._int_arg(request, "since", 0, minimum=0, maximum=10**9)
        return _json_ok(self.metrics.logs(since=since, limit=limit))

    async def tasks(self, request: web.Request) -> web.Response:
        payload: dict[str, Any] = {"scheduled": [], "background": []}
        manager = self._service("scheduled_task_manager")
        lister = getattr(manager, "list_tasks", None) if manager is not None else None
        if callable(lister):
            try:
                value = lister()
                if hasattr(value, "__await__"):
                    value = await value
                payload["scheduled"] = value if isinstance(value, list) else []
            except Exception as exc:
                payload["scheduled_error"] = str(exc)
        drawing = self._service("drawing_manager")
        status = getattr(drawing, "list_active", None) if drawing is not None else None
        if callable(status):
            try:
                payload["background"] = status()
            except Exception as exc:
                payload["background_error"] = str(exc)
        return _json_ok(payload)

    async def services(self, request: web.Request) -> web.Response:
        registry = self.console.services
        describe = getattr(registry, "describe", None) if registry is not None else None
        items: list[dict[str, Any]] = []
        if callable(describe):
            try:
                items = describe()
            except Exception:
                items = []
        return _json_ok({"items": items, "plugin_runtime": self._plugin_control() is not None})

    # ------------------------------------------------------------------
    # 插件管理
    # ------------------------------------------------------------------

    def _plugin_summary(self) -> dict[str, int]:
        control = self._plugin_control()
        if control is None:
            return {"total": 0, "loaded": 0, "error": 0}
        try:
            snapshots = control.snapshot()
        except Exception:
            return {"total": 0, "loaded": 0, "error": 0}
        return {
            "total": len(snapshots),
            "loaded": sum(1 for item in snapshots if item.state == "running"),
            "error": sum(1 for item in snapshots if item.state == "error"),
        }

    def _plugin_payload(self, snapshot: Any) -> dict[str, Any]:
        return {
            "id": snapshot.name,
            "name": snapshot.name,
            "version": snapshot.version,
            "status": _status_text(snapshot),
            "state": snapshot.state,
            "enabled": snapshot.enabled,
            "description": snapshot.description,
            "author": snapshot.author,
            "source": snapshot.source,
            "official": snapshot.official,
            "manageable": snapshot.manageable,
            "kind": snapshot.kind,
            "path": str(snapshot.path) if snapshot.path else "",
            "error": snapshot.error,
            "repo": snapshot.repo,
            "branch": snapshot.branch,
            "homepage": snapshot.homepage,
            "license": snapshot.license,
            "tags": list(snapshot.tags),
            "dependencies": list(snapshot.dependencies),
            "python_dependencies": list(snapshot.python_dependencies),
            "missing_python_dependencies": list(snapshot.missing_python_dependencies),
        }

    async def plugins(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        if control is None:
            return _json_ok(
                {
                    "items": [],
                    "manage_enabled": False,
                    "hot_reload": False,
                    "error": "插件运行时不可用",
                }
            )
        try:
            snapshots = control.snapshot()
        except Exception as exc:
            return _json_error(f"读取插件列表失败: {exc}", status=500)
        return _json_ok(
            {
                "items": [self._plugin_payload(item) for item in snapshots],
                "manage_enabled": self.console.manage_plugins,
                "hot_reload": True,
                "installer": bool(getattr(control, "installer_available", False)),
                "console_plugin": self.console.plugin_name,
            }
        )

    async def plugin_toggle(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        if snapshot is None:
            return _json_error(f"插件不存在: {name}", status=404)
        target_enabled = not bool(snapshot.enabled)
        result = await control.set_enabled(name, target_enabled)
        return _operation_response(result, f"{'已启用' if target_enabled else '已停用'} {name}")

    async def plugin_reload(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        if name == self.console.plugin_name:
            return _json_error("面板自身不支持热重载（会中断当前连接），请重启 NeoBot", status=400)
        result = await control.reload(name)
        return _operation_response(result, f"{name} 已重载")

    async def plugin_update(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        if snapshot is None:
            return _json_error(f"插件不存在: {name}", status=404)
        if snapshot.official:
            return _json_error("官方插件随本体更新，不能在面板内更新", status=400)
        if not snapshot.repo:
            return _json_error(f"插件 {name} 未声明 repo，无法更新", status=400)
        runtime = self._service("plugin_runtime")
        installer = getattr(runtime, "installer", None) if runtime is not None else None
        if installer is None:
            return _json_error("插件安装器不可用", status=503)
        result = await installer.update(name, repo=snapshot.repo, branch=snapshot.branch)
        if not result.ok:
            return _json_error(result.error or "更新失败", status=400)
        outcome = await control.reload(name)
        if outcome.ok:
            return _json_ok({"message": f"{name} 已更新至 {result.version} 并重载"})
        return _json_error(
            f"已更新至 {result.version}，但重载失败: {outcome.error or outcome.state}",
            status=500,
        )

    async def plugin_uninstall(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        if name == self.console.plugin_name:
            return _json_error("不能卸载面板自身", status=400)
        result = await control.uninstall(name)
        return _operation_response(result, f"{name} 已卸载")

    async def plugins_install(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        repo = str(payload.get("repo") or "").strip()
        branch = str(payload.get("branch") or "").strip() or None
        if not repo:
            return _json_error("请填写 GitHub 仓库地址")
        result = await control.install(repo, branch=branch, replace=bool(payload.get("replace")))
        return _operation_response(result, f"已安装 {result.name}")

    async def plugins_check_updates(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            checks = await control.check_updates()
        except Exception as exc:
            return _json_error(f"检查更新失败: {exc}", status=500)
        items = [
            {
                "name": item.name,
                "current_version": item.current_version,
                "remote_version": item.remote_version,
                "status": item.status,
                "error": item.error,
            }
            for item in checks
        ]
        available = [item for item in items if item["status"] == "available"]
        return _json_ok(
            {
                "items": items,
                "available": len(available),
                "message": (
                    f"{len(available)} 个插件可更新"
                    if available
                    else "全部插件均为最新"
                ),
            }
        )

    async def plugin_config_get(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name) if control is not None else None
        if snapshot is not None and snapshot.official:
            return _json_error(
                "官方插件配置来自 config.toml，请到「配置管理」页面修改", status=400
            )
        path = self._plugin_manifest_path(snapshot)
        if path is None:
            return _json_error(f"插件 {name} 没有 plugin.toml，无法在线编辑配置", status=404)
        try:
            document = PluginConfigEditor(path).read()
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        document["can_reload"] = True
        document["manage_enabled"] = self.console.manage_plugins
        return _json_ok(document)

    async def plugin_config_save(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name) if control is not None else None
        if snapshot is not None and snapshot.official:
            return _json_error(
                "官方插件配置来自 config.toml，请到「配置管理」页面修改", status=400
            )
        path = self._plugin_manifest_path(snapshot)
        if path is None:
            return _json_error(f"插件 {name} 没有 plugin.toml，无法在线编辑配置", status=404)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        editor = PluginConfigEditor(path)
        try:
            document = editor.save(
                config=payload.get("config"),
                source=payload.get("source"),
                expected_revision=payload.get("revision"),
            )
        except PluginConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        reload_requested = bool(payload.get("reload"))
        applied = False
        message = "配置已保存"
        if reload_requested and control is not None:
            outcome = await control.reload(name)
            applied = outcome.ok
            message = (
                f"配置已保存并重载 {name}" if outcome.ok else f"配置已保存，但重载失败: {outcome.error or outcome.state}"
            )
        document["can_reload"] = True
        document["applied"] = applied
        document["message"] = message
        return _json_ok(document)

    # ------------------------------------------------------------------
    # 本体配置 / .env
    # ------------------------------------------------------------------

    def _config_manager(self) -> BotConfigManager:
        return self.console.config_manager

    def _env_manager(self) -> EnvFileManager:
        return self.console.env_manager

    async def config_get(self, request: web.Request) -> web.Response:
        try:
            document = self._config_manager().read()
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"读取配置失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        return _json_ok(document)

    async def config_save(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._config_manager()
        try:
            document = manager.save(
                source=payload.get("source"),
                config=payload.get("config"),
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存配置失败: {exc}", status=500)
        applied = False
        message = "配置已保存"
        if payload.get("reload"):
            reload_result = await self._reload_config()
            applied = bool(reload_result.get("ok"))
            message = str(reload_result.get("message") or message)
        document["can_manage"] = self.console.manage_plugins
        document["applied"] = applied
        document["message"] = message
        return _json_ok(document)

    async def config_validate(self, request: web.Request) -> web.Response:
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        errors = self._config_manager().validate(
            source=payload.get("source"), config=payload.get("config")
        )
        if errors:
            return _json_error("配置校验未通过", status=400, errors=errors)
        return _json_ok({"message": "配置校验通过", "errors": []})

    async def config_reload(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        result = await self._reload_config()
        if result.get("ok"):
            return _json_ok(result)
        return _json_error(str(result.get("message") or "重载失败"), status=500)

    async def _reload_config(self) -> dict[str, Any]:
        commands = self._service("host_commands")
        caller = getattr(commands, "call", None) if commands is not None else None
        if not callable(caller):
            return {"ok": False, "message": "配置重载入口不可用，请重启 NeoBot"}
        try:
            result = caller("config.reload")
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            return {"ok": False, "message": f"配置重载失败: {exc}"}
        if isinstance(result, dict):
            ok = str(result.get("status") or "").lower() == "ok"
            return {"ok": ok, "message": str(result.get("message") or "")}
        return {"ok": False, "message": "配置重载返回异常"}

    async def env_get(self, request: web.Request) -> web.Response:
        try:
            document = self._env_manager().read(mask=True)
        except Exception as exc:
            return _json_error(f"读取 .env 失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        return _json_ok(document)

    async def env_reveal(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request, action="显示密钥")
        if denied is not None:
            return denied
        key = request.match_info["key"]
        try:
            value = self._env_manager().reveal(key)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400)
        self.logger.info(f"面板显示密钥 ip={self.console.request_ip(request)} key={key}")
        return _json_ok({"key": key, "value": value})

    async def env_save(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._env_manager()
        try:
            document = manager.save(
                updates=payload.get("updates") or {},
                deletes=payload.get("deletes") or [],
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存 .env 失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        document["message"] = "环境变量已保存；模型注册表需重载后生效"
        if payload.get("reload"):
            reload_result = await self._reload_config()
            document["applied"] = bool(reload_result.get("ok"))
            document["message"] = str(reload_result.get("message") or document["message"])
        return _json_ok(document)

    async def config_models(self, request: web.Request) -> web.Response:
        try:
            payload = models_view()
        except Exception as exc:
            return _json_error(f"读取模型注册表失败: {exc}", status=500)
        payload["can_manage"] = self.console.manage_plugins
        return _json_ok(payload)

    async def admin_restart(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        application = self._service("application")
        restart = getattr(application, "request_restart", None) if application is not None else None
        if not callable(restart):
            return _json_error("重启入口不可用，请手动重启 NeoBot", status=503)
        self.logger.warning(f"面板请求重启 NeoBot ip={self.console.request_ip(request)}")
        asyncio.get_running_loop().call_later(0.5, restart)
        return _json_ok({"message": "已请求优雅重启，面板将在重启期间短暂不可用"})

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _int_arg(
        request: web.Request, name: str, default: int, *, minimum: int, maximum: int
    ) -> int:
        raw = request.query.get(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _find_snapshot(control: Any, name: str) -> Any:
        if control is None:
            return None
        try:
            snapshots = control.snapshot()
        except Exception:
            return None
        for item in snapshots:
            if item.name == name:
                return item
        return None

    @staticmethod
    def _plugin_manifest_path(snapshot: Any) -> Path | None:
        path = getattr(snapshot, "path", None)
        if path is None:
            return None
        candidate = Path(path)
        if candidate.is_dir():
            manifest = candidate / "plugin.toml"
        else:
            manifest = candidate.parent / "plugin.toml"
        return manifest if manifest.is_file() else None


def _status_text(snapshot: Any) -> str:
    if not getattr(snapshot, "enabled", True):
        return "disabled"
    state = str(getattr(snapshot, "state", "") or "")
    if state == "error":
        return "error"
    if state == "running":
        return "loaded"
    if state in {"stopped", "unloaded"}:
        return "unloaded" if getattr(snapshot, "enabled", True) else "disabled"
    return state or "unloaded"


def _operation_response(result: Any, success_message: str) -> web.Response:
    if getattr(result, "ok", False):
        return _json_ok(
            {
                "message": success_message,
                "name": getattr(result, "name", ""),
                "state": getattr(result, "state", None),
                "requires_restart": bool(getattr(result, "requires_restart", False)),
            }
        )
    return _json_error(
        str(getattr(result, "error", "") or "操作失败"),
        status=400,
        name=getattr(result, "name", ""),
        state=getattr(result, "state", None),
    )
