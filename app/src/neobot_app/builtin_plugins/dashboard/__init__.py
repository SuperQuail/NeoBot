"""NeoBot 官方网页面板插件。

- 配置直接读取本体 config.toml 的 [dashboard] 分区（官方插件配置由本体注入）。
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
        if not config.enabled:
            ctx.logger.info("网页面板已禁用（dashboard.enabled=false），跳过启动")
            return

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
