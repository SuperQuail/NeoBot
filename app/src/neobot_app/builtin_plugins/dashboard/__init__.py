"""NeoBot 官方网页面板插件。

- 配置来自插件数据目录 plugins_data/dashboard/config.toml（与本体 config.toml 无关）。
- 面板是否启用由 plugin_state.json 的独立记录决定，不写在配置里。
- 默认监听 0.0.0.0:9981，对网络开放；host/port/base_path 均可配置。
- 完全取代旧的内置调试控制台与管理员控制台：运行监测、日志、插件管理、
  本体配置与 .env 在线编辑、模型注册表查看、优雅重启。
"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_modloader import Plugin

from .config import DashboardConfig
from .server import DashboardServer

plugin = Plugin(
    "dashboard",
    version="1.0.0",
    description="NeoBot 网页面板：运行监测、日志、插件管理、本体配置在线编辑",
    author="NeoBot",
    config=DashboardConfig,
    # 面板自身持有 HTTP 服务与监听端口：热重载会中断当前连接，配置改动也需重启绑定
    hot_reload=False,
    config_hot_reload=False,
)

LATENCY_INTERVAL_SECONDS = 15.0


class DashboardPlugin:
    """面板插件运行时状态。"""

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: DashboardConfig | None = None
        self.server: DashboardServer | None = None
        self._latency_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------

    async def load(self, ctx: Any) -> None:
        self.ctx = ctx
        self.config = ctx.config if isinstance(ctx.config, DashboardConfig) else DashboardConfig.model_validate(dict(ctx.config or {}))
        config = self.config

        from neobot_app.core import CONFIG_BACKUP_DIR, CONFIG_FILE, ENV_FILE

        services = getattr(getattr(ctx, "plugin_host", None), "services", None)
        host_commands = None
        host_facade = getattr(ctx, "plugin_host", None)
        if host_facade is not None:
            host_commands = getattr(host_facade, "commands", None)

        server = DashboardServer(
            plugin_name=ctx.plugin_name,
            config=config,
            data_dir=ctx.data_dir,
            logger=ctx.logger,
            adapter=getattr(ctx, "adapter", None),
            plugin_control=getattr(ctx, "plugin_control", None),
            services=services,
            config_path=CONFIG_FILE,
            env_path=ENV_FILE,
            backup_dir=CONFIG_BACKUP_DIR,
            host_commands=host_commands,
        )
        self.server = server
        try:
            await server.start()
        except OSError as exc:
            ctx.logger.error(f"网页面板启动失败: {exc}")
            self.server = None
            return

        from . import system as system_module

        system_module.prime()

        hook_bus = getattr(ctx, "hook_bus", None)
        if hook_bus is not None:
            subscription = hook_bus.subscribe_runtime(self._on_runtime_event, kind="log")
            if subscription is not None:
                ctx.record_subscription(subscription)

        self._latency_task = asyncio.create_task(self._latency_loop())

    async def unload(self) -> None:
        if self._latency_task is not None:
            self._latency_task.cancel()
            try:
                await self._latency_task
            except (asyncio.CancelledError, Exception):
                pass
            self._latency_task = None
        if self.server is not None:
            await self.server.stop()
            self.server = None

    async def _on_runtime_event(self, envelope: Any) -> Any:
        server = self.server
        if server is None:
            return envelope
        try:
            payload = getattr(envelope, "payload", None) or {}
            if isinstance(payload, dict):
                server.metrics.record_log(payload)
        except Exception:
            pass
        return envelope

    async def _latency_loop(self) -> None:
        await asyncio.sleep(3.0)
        while True:
            server = self.server
            if server is None:
                return
            try:
                await server.probe_latency()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            try:
                await asyncio.sleep(LATENCY_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise


_instance = DashboardPlugin()


# ── 对外能力：依赖面板的插件通过 ctx.require_plugin("dashboard") 调用 ──


@plugin.capability("web.register_extension")
async def _register_web_extension(payload: Any) -> str:
    """把插件自己的页面 / 接口挂到面板的端口上。

    调用方::

        handle = ctx.require_plugin("dashboard", ">=1.0.0")
        prefix = await handle.call(
            "web.register_extension",
            {"name": "starship", "extension": extension},
        )
    """
    server = _instance.server
    if server is None:
        raise RuntimeError("网页面板服务未启动，无法挂载扩展")
    data = payload if isinstance(payload, dict) else {}
    return server.register_extension(str(data.get("name") or ""), data.get("extension"))


@plugin.capability("web.unregister_extension")
async def _unregister_web_extension(payload: Any) -> bool:
    """注销先前注册的扩展（插件卸载 / 停用时调用）。"""
    server = _instance.server
    if server is None:
        return False
    data = payload if isinstance(payload, dict) else {}
    return server.unregister_extension(str(data.get("name") or ""))


@plugin.capability("server.describe")
async def _describe_server(payload: Any) -> dict[str, Any]:
    """面板自身的运行信息（地址、端口、扩展列表）。"""
    server = _instance.server
    if server is None:
        return {"available": False}
    return {"available": True, **server.describe()}


@plugin.on_load
async def _dashboard_load(ctx: Any) -> None:
    await _instance.load(ctx)


@plugin.on_shutdown
async def _dashboard_shutdown() -> None:
    await _instance.unload()


@plugin.message(priority=-100)
async def _dashboard_count_message(event: dict[str, Any]) -> None:
    """统计消息量与活跃用户（不拦截消息，不影响 AI 回复）。"""
    server = _instance.server
    if server is None:
        return
    if str(event.get("post_type") or "") != "message":
        return
    try:
        await server.metrics.record_message(event)
    except Exception:
        pass
