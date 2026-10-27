"""基础设施：构造、服务定位与管理权限校验。"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from ..security import is_loopback
from ._common import _json_error


class DashboardApiBase:
    #: 聊天流可读名称的缓存 TTL（秒）。面板 5s 轮询、最多 128 条流，
    #: 没有缓存就会变成「每轮每流一次 DB 查询」（features/spec(3) §4.5 A12）。
    DISPLAY_NAME_TTL_SECONDS = 60.0

    def __init__(self, *, console: Any) -> None:
        self.console = console
        #: 后台电源动作的强引用：create_task 的返回值被丢弃时任务可能被 GC 回收
        self._power_tasks: set[asyncio.Task[Any]] = set()
        #: pipeline_key -> 可读名称（TTL 见 DISPLAY_NAME_TTL_SECONDS）
        self._display_names: dict[str, str] = {}
        self._display_names_at = 0.0
        #: 按插件串行校验启停状态，避免旧页面覆盖新选择。
        self._plugin_toggle_locks: dict[str, asyncio.Lock] = {}

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

    def _standby_service(self) -> Any:
        return self._service("standby_service")

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
