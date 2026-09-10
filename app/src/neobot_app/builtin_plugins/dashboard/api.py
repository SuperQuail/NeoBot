"""网页面板 HTTP 接口实现。

所有写操作都经过 _require_manage 校验（manage_plugins / allow_remote_manage），
所有响应都只暴露必要信息，密钥类字段默认打码。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp import web

from . import system as system_module
from .config_manager import (
    BotConfigManager,
    ConfigConflictError,
    ConfigValidationError,
    EnvFileManager,
    describe_pydantic_model,
    models_view,
)
from .model_probe import list_provider_models
from .plugin_config import PluginConfigConflictError, PluginConfigEditor, PluginConfigError
from neobot_app.panel_auth import PasswordPolicyError

from .security import is_loopback


def _pydantic_errors(exc: Any) -> list[dict[str, str]]:
    """把 pydantic 校验错误转换为面板统一的 {path, message} 列表。"""
    errors: list[dict[str, str]] = []
    raw = getattr(exc, "errors", None)
    if callable(raw):
        try:
            for item in raw():
                location = item.get("loc") or ()
                errors.append(
                    {
                        "path": ".".join(str(part) for part in location) or "config",
                        "message": str(item.get("msg") or "取值非法"),
                    }
                )
        except Exception:
            errors = []
    if not errors:
        errors.append({"path": "config", "message": str(exc)})
    return errors


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

    def _freeze_service(self) -> Any:
        return self._service("freeze_service")

    def _require_manage(self, request: web.Request, *, action: str = "管理操作") -> web.Response | None:
        if not self.console.manage_plugins:
            return _json_error("面板已禁用管理功能（dashboard.manage_plugins=false）", status=403)
        if not self.console.allow_remote_manage and not is_loopback(self.console.request_ip(request)):
            return _json_error(
                "远程管理已关闭（dashboard.allow_remote_manage=false），请在本机操作",
                status=403,
            )
        return None

    def _can_manage(self, request: web.Request) -> bool:
        """是否有管理权限（与 _require_manage 同判据，用于按权限裁剪响应）。"""
        return self.console.manage_plugins and (
            self.console.allow_remote_manage
            or is_loopback(self.console.request_ip(request))
        )

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
        ip = self.console.request_ip(request)
        loopback = is_loopback(ip)
        configured = self.console.passwords.configured
        return _json_ok(
            {
                "authenticated": False,
                "configured": configured,
                "setup_required": not configured,
                "setup_allowed": (not configured) and loopback,
                "loopback": loopback,
                "can_manage": configured
                and self.console.manage_plugins
                and (self.console.allow_remote_manage or loopback),
                "base_path": self.console.base_path,
                "version": self.console.version,
            }
        )

    async def auth_setup(self, request: web.Request) -> web.Response:
        """本机首次设置面板密码（未设置密码时仅回环地址可用）。"""
        ip = self.console.request_ip(request)
        if self.console.passwords.configured:
            return _json_error("面板密码已设置，请直接登录", status=400)
        if not is_loopback(ip):
            return _json_error(
                "只能在本机设置面板密码；外网访问请由超级管理员在 QQ 私聊发送 /set_password 设置",
                status=403,
            )
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        password = str(payload.get("password") or "")
        confirm = str(payload.get("confirm") or "")
        if confirm and confirm != password:
            return _json_error("两次输入的密码不一致")
        try:
            self.console.passwords.set_password(password)
        except PasswordPolicyError as exc:
            return _json_error(str(exc))
        session = self.console.create_session(request)
        response = _json_ok(
            {
                "token": session.token,
                "csrf_token": session.csrf_token,
                "message": "面板密码已设置，登录成功",
                "session": session.to_payload(
                    timeout_seconds=self.console.sessions.timeout_seconds
                ),
            }
        )
        self.console.set_session_cookie(response, session.token)
        self.logger.warning(f"面板密码已设置 ip={ip}")
        return response

    async def auth_me(self, request: web.Request) -> web.Response:
        session = request.get("dashboard_session")
        ip = self.console.request_ip(request)
        return _json_ok(
            {
                "authenticated": True,
                "configured": self.console.passwords.configured,
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
        supplied = str(payload.get("password") or "")
        if not self.console.passwords.configured:
            return _json_error(
                "面板尚未设置密码，请在本机设置或由超级管理员在 QQ 私聊发送 /set_password",
                status=403,
                setup_required=True,
            )
        if not self.console.verify_password(supplied):
            self.console.limiter.record_failure(ip)
            self.logger.warning(f"面板登录失败 ip={ip}")
            return _json_error("密码不正确", status=401)
        self.console.limiter.reset(ip)
        session = self.console.create_session(request)
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
                "frozen": self.frozen_state()["frozen"],
            }
        )

    def frozen_state(self) -> dict[str, Any]:
        """当前冻结状态；冻结服务未注册时返回 available=False。"""
        service = self._freeze_service()
        if service is None:
            return {"available": False, "frozen": False}
        try:
            status = dict(service.status())
        except Exception:
            return {"available": False, "frozen": False}
        status["available"] = True
        return status

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

    async def series_usage(self, request: web.Request) -> web.Response:
        """用量图表：按小时/天汇总金额与 Token，并给出模型/模块排行。"""
        hours = self._int_arg(request, "hours", 24, minimum=1, maximum=24 * 365)
        bucket = str(request.query.get("bucket") or "hour").strip().lower()
        if bucket not in {"hour", "day"}:
            bucket = "hour"
        session_factory = self._service("usage_session_factory")
        if session_factory is None:
            return _json_ok(
                {
                    "available": False,
                    "bucket": bucket,
                    "hours": hours,
                    "points": [],
                    "models": [],
                    "modules": [],
                    "totals": {},
                }
            )
        try:
            import datetime as _dt

            from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                points = await repo.series_since(cutoff, bucket=bucket)
                models = await repo.breakdown_by_model_since(cutoff, limit=12)
                modules = await repo.breakdown_by_module_since(cutoff, limit=12)
        except Exception as exc:
            self.logger.warning(f"读取用量图表失败: {exc}")
            return _json_ok(
                {
                    "available": False,
                    "bucket": bucket,
                    "hours": hours,
                    "points": [],
                    "models": [],
                    "modules": [],
                    "totals": {},
                    "error": str(exc),
                }
            )
        totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
        for point in points:
            totals["calls"] += int(point["calls"])
            totals["input_tokens"] += int(point["input_tokens"])
            totals["output_tokens"] += int(point["output_tokens"])
            totals["cost_cny"] += float(point["cost_cny"])
        totals["cost_cny"] = round(totals["cost_cny"], 6)
        return _json_ok(
            {
                "available": True,
                "bucket": bucket,
                "hours": hours,
                "currency": "CNY",
                "points": points,
                "models": models,
                "modules": modules,
                "totals": totals,
            }
        )

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
        elif manager is not None:
            # 显式报错而不是静默留空：接口改名/缺失时面板会直接显示原因，
            # 不会让「定时任务列表恒为空」这种问题再次无声无息。
            payload["scheduled_error"] = "scheduled_task_manager 未提供 list_tasks 接口"
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
            "hot_reload": bool(getattr(snapshot, "hot_reload", True)),
            "config_hot_reload": bool(getattr(snapshot, "config_hot_reload", True)),
            "hot_reloadable": bool(getattr(snapshot, "hot_reloadable", True)),
            "config_path": str(self._plugin_config_path(snapshot.name) or ""),
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
                "proxy": self._installer_proxy(control),
                "proxy_modes": ["system", "none", "custom"],
            }
        )

    def _installer_proxy(self, control: Any) -> dict[str, Any]:
        getter = getattr(control, "installer_proxy", None)
        if callable(getter):
            try:
                return dict(getter())
            except Exception:
                return {}
        return {}

    def _plugin_config_path(self, name: str) -> Path | None:
        """插件配置文件路径（插件数据目录下的 config.toml）。"""
        control = self._plugin_control()
        if control is None:
            return None
        getter = getattr(control, "plugin_config_path", None)
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    def _plugin_config_editor(self, control: Any, name: str) -> PluginConfigEditor | None:
        path = self._plugin_config_path(name)
        if path is None:
            return None
        defaults: dict[str, Any] = {}
        getter = getattr(control, "plugin_config_defaults", None)
        if callable(getter):
            try:
                defaults = dict(getter(name))
            except Exception:
                defaults = {}
        return PluginConfigEditor(path, defaults=defaults)

    def _plugin_config_meta(
        self, snapshot: Any, name: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        """插件配置文档的公共元信息（官方与第三方插件一致）。"""
        official = bool(getattr(snapshot, "official", False))
        hot_reload = bool(getattr(snapshot, "hot_reload", True))
        document.update(
            {
                "name": name,
                "version": str(getattr(snapshot, "version", "") or ""),
                "official": official,
                "manage_enabled": self.console.manage_plugins,
                "can_reload": hot_reload,
                "hot_reload": hot_reload,
                "config_hot_reload": bool(
                    getattr(snapshot, "config_hot_reload", True)
                ),
                "message": "插件配置保存在插件数据目录，与插件代码和启停状态分离",
            }
        )
        return document

    async def plugins_proxy_save(self, request: web.Request) -> web.Response:
        """插件下载代理设置：写入 config.toml 的 [plugins] 并立即生效。"""
        denied = self._require_manage(request, action="修改插件代理设置")
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        setter = getattr(control, "set_installer_proxy", None)
        if not callable(setter):
            return _json_error("插件安装器不可用", status=503)
        mode = str(payload.get("mode") or "system").strip().lower()
        host = str(payload.get("host") or "127.0.0.1").strip()
        try:
            port = int(payload.get("port") or 7890)
        except (TypeError, ValueError):
            return _json_error("代理端口必须是数字", status=400)
        try:
            settings = setter(mode=mode, host=host, port=port)
        except Exception as exc:
            return _json_error(f"代理设置无效: {exc}", status=400)
        if payload.get("persist", True):
            try:
                self._config_manager().update_plugins_proxy(
                    mode=mode,
                    host=host,
                    port=port,
                    expected_revision=payload.get("revision"),
                )
            except ConfigConflictError as exc:
                return _json_error(str(exc), status=409)
            except ConfigValidationError as exc:
                return _json_error(str(exc), status=400, errors=exc.errors)
            except Exception as exc:
                return _json_error(f"保存代理设置失败: {exc}", status=500)
        return _json_ok(
            {
                "message": f"插件下载代理已切换为{settings.get('description') or mode}",
                "proxy": settings,
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
        if name == self.console.plugin_name:
            return _json_error(
                "不能从面板内部停用面板自身；如需关闭网页面板，"
                "请把 data/plugin_state.json 里 dashboard 的 enabled 改为 false 后重启 NeoBot",
                status=400,
            )
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
        """插件配置：读取插件数据目录下的 config.toml（官方/第三方同一路径）。"""
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        editor = self._plugin_config_editor(control, name)
        if editor is None:
            return _json_error(f"插件不存在或没有独立数据目录: {name}", status=404)
        try:
            document = editor.read()
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        model = control.config_model(name)
        schema = describe_pydantic_model(model, document.get("config") or {})
        if schema:
            # 插件声明了 pydantic 模型时以模型为准（带范围/标题/说明）
            document["schema"] = schema
            document["form_supported"] = True
        return _json_ok(self._plugin_config_meta(snapshot, name, document))

    async def plugin_config_save(self, request: web.Request) -> web.Response:
        """插件配置：写入插件数据目录下的 config.toml，可选立即重载插件。"""
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        editor = self._plugin_config_editor(control, name)
        if editor is None:
            return _json_error(f"插件不存在或没有独立数据目录: {name}", status=404)
        values = payload.get("config")
        if not isinstance(values, dict):
            values = payload.get("values")
        model = control.config_model(name)
        if model is not None and isinstance(values, dict):
            defaults: dict[str, Any] = {}
            getter = getattr(control, "plugin_config_defaults", None)
            if callable(getter):
                try:
                    defaults = dict(getter(name))
                except Exception:
                    defaults = {}
            try:
                model.model_validate({**defaults, **values})
            except Exception as exc:
                return _json_error(
                    "插件配置校验失败", status=400, errors=_pydantic_errors(exc)
                )
        try:
            document = editor.save(
                config=values if isinstance(values, dict) else None,
                source=payload.get("source"),
                expected_revision=payload.get("revision"),
            )
        except PluginConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        schema = describe_pydantic_model(model, document.get("config") or {})
        if schema:
            document["schema"] = schema
        applied = False
        message = "配置已保存到插件数据目录"
        reload_requested = bool(payload.get("reload"))
        if reload_requested:
            if bool(getattr(snapshot, "config_hot_reload", True)):
                outcome = await control.reload(name)
                applied = outcome.ok
                message = (
                    f"配置已保存并重载 {name}"
                    if outcome.ok
                    else f"配置已保存，但重载失败: {outcome.error or outcome.state}"
                )
            else:
                message += "；该插件配置需要重启 NeoBot 才能生效"
        document["applied"] = applied
        document["message"] = message
        return _json_ok(self._plugin_config_meta(snapshot, name, document))

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
        if not self._can_manage(request):
            # config.toml 里也有机密（adapter.local_auth_token /
            # adapter.reverse_ws_access_token）。结构化 config/schema 已按字段掩码，
            # 但原文与 raw 副本同样带明文，只读会话不得获取——与 .env 侧
            # 「密钥只回是否已设置」的约定保持一致。
            document["source"] = ""
            document["raw"] = {}
            document["secrets_hidden"] = True
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
            reload_result = await self._reload_config(with_changes=True)
            applied = bool(reload_result.get("ok"))
            message = str(reload_result.get("message") or message)
            if reload_result.get("changes"):
                document["changes"] = reload_result["changes"]
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
        """不重启进程的热重载：重载配置并返回「已生效 / 需重启」明细。"""
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        result = await self._reload_config(with_changes=True)
        if result.get("ok"):
            return _json_ok(result)
        return _json_error(str(result.get("message") or "重载失败"), status=500)

    async def _reload_config(self, *, with_changes: bool = False) -> dict[str, Any]:
        from neobot_app.config.hot_reload import diff_snapshot, snapshot, summarize_changes

        before: dict[str, Any] | None = None
        if with_changes:
            config_obj = self._models_config()
            if config_obj is not None:
                try:
                    before = snapshot(config_obj)
                except Exception:
                    before = None

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
        if not isinstance(result, dict):
            return {"ok": False, "message": "配置重载返回异常"}
        ok = str(result.get("status") or "").lower() == "ok"
        payload: dict[str, Any] = {"ok": ok, "message": str(result.get("message") or "")}
        if ok and before is not None:
            after = self._models_config()
            if after is not None:
                try:
                    changes = diff_snapshot(before, after)
                    payload["changes"] = summarize_changes(changes)
                    if changes:
                        payload["message"] = (
                            f"配置已热重载：{payload['changes']['hot_reload_count']} 项已生效，"
                            f"{payload['changes']['needs_restart_count']} 项需重启"
                        )
                    else:
                        payload["message"] = "配置已重载，本次没有检测到配置项变化"
                except Exception as exc:
                    self.logger.warning(f"配置差异计算失败: {exc}")
        return payload

    async def env_get(self, request: web.Request) -> web.Response:
        try:
            document = self._env_manager().read(mask=True)
        except Exception as exc:
            return _json_error(f"读取 .env 失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        return _json_ok(document)

    async def env_platform_add(self, request: web.Request) -> web.Response:
        """一键添加 API 供应商：写入 <平台名>_URL / <平台名>_APIKey（Key 只写不读）。"""
        denied = self._require_manage(request, action="添加 API 供应商")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._env_manager()
        try:
            document = manager.add_platform(
                name=str(payload.get("name") or ""),
                url=str(payload.get("url") or ""),
                api_key=str(payload.get("api_key") or payload.get("apiKey") or ""),
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"添加供应商失败: {exc}", status=500)
        self.logger.info(
            f"面板添加 API 供应商 ip={self.console.request_ip(request)} name={payload.get('name')}"
        )
        document["can_manage"] = self.console.manage_plugins
        document["message"] = "供应商已写入 .env（API Key 只写不读，可在模型库中引用该平台）"
        if payload.get("reload"):
            reload_result = await self._reload_config()
            document["applied"] = bool(reload_result.get("ok"))
            document["message"] = str(reload_result.get("message") or document["message"])
        return _json_ok(document)

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

    def _models_config(self) -> Any:
        """读取模型库：以 config.toml 为准，读不到时退回运行中的配置。

        面板编辑的是文件，若优先用运行中的配置对象，保存后（未重载）列表不会更新，
        刷新页面也看不到新模型，因此这里以文件解析结果为主。
        """
        try:
            instance = self._config_manager().instance()
            if hasattr(instance, "models"):
                return instance
        except Exception as exc:
            self.logger.warning(f"读取 config.toml 失败，改用运行中配置: {exc}")
        config_obj = self._config_proxy()
        if config_obj is not None and hasattr(config_obj, "models"):
            return config_obj
        return None

    async def config_models(self, request: web.Request) -> web.Response:
        try:
            payload = models_view(self._models_config())
        except Exception as exc:
            return _json_error(f"读取模型注册表失败: {exc}", status=500)
        # 把 .env 里的自定义平台合并进供应商候选（面板添加供应商后立即可选）
        try:
            env_platforms = {str(item.get("name") or "") for item in self._env_manager().platforms()}
            merged = set(payload.get("provider_options") or []) | {name for name in env_platforms if name}
            payload["provider_options"] = sorted(merged, key=str.casefold)
            payload["platforms"] = self._env_manager().platforms()
        except Exception as exc:
            self.logger.warning(f"读取平台列表失败: {exc}")
        payload["can_manage"] = self.console.manage_plugins
        try:
            payload["revision"] = self._config_manager().revision()
        except Exception:
            payload["revision"] = ""
        return _json_ok(payload)

    async def models_provider_models(self, request: web.Request) -> web.Response:
        """拉取某个供应商的可用模型列表（供模型编辑时选择）。"""
        denied = self._require_manage(request, action="拉取供应商模型列表")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        from neobot_app.config.schemas.env import EnvConfig

        provider = str(payload.get("provider") or "").strip()
        if not provider:
            return _json_error("请先选择供应商", status=400)
        platform = EnvConfig.get_api_platform_config(provider)
        if not platform or not platform.url:
            return _json_error(f"供应商 {provider} 未配置 URL（请在环境变量中填写 {provider}_URL）", status=400)
        try:
            timeout = float(payload.get("timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        result = await list_provider_models(
            base_url=platform.url or "",
            api_key=platform.api_key or "",
            use_system_proxy=bool(payload.get("use_system_proxy", False)),
            timeout=max(3.0, min(timeout, 60.0)),
        )
        data = result.to_dict()
        data["provider"] = provider
        self.logger.info(
            f"面板拉取供应商模型 ip={self.console.request_ip(request)} "
            f"provider={provider} ok={result.ok} count={len(result.models)}"
        )
        return _json_ok(data)

    async def models_library_save(self, request: web.Request) -> web.Response:
        """模型库条目新增/更新/删除（只改 config.toml 的 [models.registry]）。"""
        denied = self._require_manage(request, action="修改模型库")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        action = str(payload.get("action") or "upsert").strip().lower()
        if action not in {"upsert", "delete"}:
            return _json_error("action 只能是 upsert 或 delete", status=400)
        manager = self._config_manager()
        resolved: dict[str, Any] = {}
        try:
            if action == "delete":
                document = manager.update_models(
                    delete=str(payload.get("key") or ""),
                    expected_revision=payload.get("revision"),
                )
            else:
                document = manager.update_models(
                    upsert=payload.get("entry") or payload.get("config") or {},
                    expected_revision=payload.get("revision"),
                    resolved=resolved,
                )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存模型库失败: {exc}", status=500)
        response = await self._finish_config_write(
            request, document, payload, "模型库已保存"
        )
        if resolved.get("key"):
            try:
                body = json.loads(response.body.decode("utf-8"))
            except Exception:
                return response
            body["saved_key"] = resolved["key"]
            return web.json_response(body)
        return response

    async def models_test(self, request: web.Request) -> web.Response:
        """测试模型连通性：网络是否可达、鉴权是否通过、模型名是否存在。

        传 `key` 测试模型库中已保存的条目；传 `entry` 测试尚未保存的草稿。
        代理行为跟随条目的 `use_system_proxy`（默认直连）。
        """
        denied = self._require_manage(request, action="测试模型连通性")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        from neobot_app.config.schemas.env import EnvConfig

        from .model_probe import probe_model

        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else None
        key = str(payload.get("key") or "").strip()
        if entry is None:
            config_obj = self._models_config()
            models_config = getattr(config_obj, "models", None) if config_obj else None
            definition = models_config.get(key) if models_config is not None else None
            if definition is None:
                return _json_error(f"模型库中不存在 {key}", status=404)
            entry = {
                "provider": getattr(definition, "provider", ""),
                "model_name": getattr(definition, "model_name", ""),
                "use_system_proxy": bool(
                    getattr(definition, "use_system_proxy", False)
                ),
            }
        provider = str(entry.get("provider") or "").strip()
        model_name = str(entry.get("model_name") or "").strip()
        use_system_proxy = bool(entry.get("use_system_proxy", False))
        platform = EnvConfig.get_api_platform_config(provider) if provider else None
        try:
            timeout = float(payload.get("timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(3.0, min(timeout, 120.0))

        result = await probe_model(
            provider=provider,
            model_name=model_name,
            base_url=(platform.url if platform else "") or "",
            api_key=(platform.api_key if platform else "") or "",
            use_system_proxy=use_system_proxy,
            timeout=timeout,
        )
        data = result.to_dict()
        data.update(
            {
                "key": key,
                "provider": provider,
                "model_name": model_name,
                "has_credentials": bool(platform and platform.url and platform.api_key),
            }
        )
        self.logger.info(
            f"面板测试模型 ip={self.console.request_ip(request)} key={key or '-'} "
            f"ok={result.ok} status={result.status} proxy={use_system_proxy}"
        )
        return _json_ok(data)

    async def models_assignments_save(self, request: web.Request) -> web.Response:
        """调用方 -> 模型 key 分配（只改 config.toml 的 [models.assignments]）。"""
        denied = self._require_manage(request, action="修改模型分配")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        assignments = payload.get("assignments")
        if not isinstance(assignments, dict):
            return _json_error("assignments 必须是对象", status=400)
        try:
            document = self._config_manager().update_models(
                assignments=assignments,
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存模型分配失败: {exc}", status=500)
        return await self._finish_config_write(request, document, payload, "模型分配已保存")

    async def _finish_config_write(
        self,
        request: web.Request,
        document: dict[str, Any],
        payload: dict[str, Any],
        message: str,
    ) -> web.Response:
        """写配置后的统一收尾：可选重载 + 返回最新配置与模型视图。"""
        document["can_manage"] = self.console.manage_plugins
        document["message"] = message
        if payload.get("reload"):
            reload_result = await self._reload_config(with_changes=True)
            document["applied"] = bool(reload_result.get("ok"))
            document["message"] = str(reload_result.get("message") or message)
            if reload_result.get("changes"):
                document["changes"] = reload_result["changes"]
        try:
            document["models"] = models_view(self._models_config())
        except Exception:
            document["models"] = None
        self.logger.info(
            f"面板修改配置 ip={self.console.request_ip(request)} action={message}"
        )
        return _json_ok(document)

    # ------------------------------------------------------------------
    # 运维冻结（事故熔断）
    # ------------------------------------------------------------------

    async def freeze_status(self, request: web.Request) -> web.Response:
        return _json_ok(self.frozen_state())

    async def admin_freeze(self, request: web.Request) -> web.Response:
        """冻结 Bot：停掉回复管线与档案自动总结，进程继续运行。

        事故中最重要的能力是「立刻停火」——不需要重启进程、也不依赖命令通道。
        """
        denied = self._require_manage(request, action="冻结 Bot")
        if denied is not None:
            return denied
        service = self._freeze_service()
        if service is None:
            return _json_error("冻结服务不可用，请重启 NeoBot", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        raw_seconds = payload.get("seconds")
        seconds: float | None = None
        if raw_seconds not in (None, ""):
            try:
                seconds = float(raw_seconds)
            except (TypeError, ValueError):
                return _json_error("seconds 必须是数字（秒），留空表示一直冻结")
        reason = str(payload.get("reason") or "").strip()
        ok, message = service.freeze(
            reason=reason or "panel",
            operator=f"panel:{self.console.request_ip(request)}",
            seconds=seconds,
        )
        if not ok:
            return _json_error(message)
        self.logger.warning(
            f"面板请求冻结 Bot ip={self.console.request_ip(request)} reason={reason or 'panel'}"
        )
        return _json_ok({**self.frozen_state(), "message": message})

    async def admin_unfreeze(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request, action="解冻 Bot")
        if denied is not None:
            return denied
        service = self._freeze_service()
        if service is None:
            return _json_error("冻结服务不可用，请重启 NeoBot", status=503)
        _was_frozen, message = service.unfreeze(
            reason="panel", operator=f"panel:{self.console.request_ip(request)}"
        )
        self.logger.warning(f"面板请求解冻 Bot ip={self.console.request_ip(request)}")
        return _json_ok({**self.frozen_state(), "message": message})

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
