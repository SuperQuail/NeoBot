"""NeoBot 官方插件：DSH 任务路由（复杂开发任务分派）。

职责边界：

- **插件**负责业务：提案 / 派发 / 任务表 / 审批 / 通知 / 回收；
- **本体**负责传输与工具面：``dsh_gateway``（daemon 出站同步）、``router_mode``
  （聊天流进入受限工具面并注入任务表）、``notification_hub``（后台通知投递）。

生命周期（照 streaming_parser 的模板）：

- ``on_load``：读配置、建 store/service、注册网关 handler、注册任务表 provider、注册 /dsh；
- ``on_startup``：起一个 60s 的回收协程（stale 标记 + Router 空闲退出）；
- ``on_shutdown``：先停协程，再注销 handler 与 provider（热重载时不会残留旧对象）。

网关或 Router 模式服务缺失（本体配置关闭 / 未装配）时插件照常加载，
工具只返回「未启用」提示，不抛异常。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from neobot_modloader import Plugin

from . import tools
from .config import DshRouterConfig
from .service import DshRouterService
from .store import TaskStore

PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "DSH 任务路由：把复杂开发任务分派给本机 DSH daemon（提案 → 派发 → 进度/卡点通知 → 审批 → 回收）"

#: 回收协程的扫描周期（秒）。
HEARTBEAT_SECONDS = 60.0

plugin = Plugin(
    "dsh_router",
    version=PLUGIN_VERSION,
    description=PLUGIN_DESCRIPTION,
    author="NeoBot",
    config=DshRouterConfig,
    dependencies=(),
    hot_reload=True,
    config_hot_reload=True,
)

tools.register(plugin)


class PluginState:
    """插件运行时状态；热重载会整体换一个新实例。"""

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: DshRouterConfig | None = None
        self.service: DshRouterService | None = None
        self.gateway: Any = None
        self.router_mode: Any = None
        self.heartbeat: asyncio.Task[None] | None = None


state = PluginState()


def _host_service(ctx: Any, name: str) -> Any:
    """按名取宿主服务；缺失/异常一律返回 None（不能因为服务表异常阻断加载）。"""
    try:
        services = ctx.plugin_host.services
    except Exception:
        return None
    try:
        return services.get(name)
    except Exception:
        return None


def _bind_required_skills(router_mode: Any, names: tuple[str, ...], logger: Any) -> None:
    """把 Router 模式需要预激活的技能包告诉宿主（老核心没有该钩子时静默跳过）。

    工具默认是按需加载的，Router 模式每轮新建执行器会丢掉加载状态；
    宿主据此在每轮构建工具表前预激活 ``dsh_router``，否则模型看不到
    ``dsh_router__send/status/cancel``。
    """
    setter = getattr(router_mode, "set_required_skills", None)
    if not callable(setter):
        return
    try:
        setter(names)
    except Exception as exc:
        warn = getattr(logger, "warning", None)
        if callable(warn):
            warn(f"注册 Router 模式预激活技能失败: {exc}")


def _coerce_config(raw: Any) -> DshRouterConfig:
    if isinstance(raw, DshRouterConfig):
        return raw
    dump = getattr(raw, "model_dump", None)
    if callable(dump):
        return DshRouterConfig(**dump())
    if isinstance(raw, dict):
        return DshRouterConfig(**raw)
    return DshRouterConfig()


async def _heartbeat_loop(service: DshRouterService, logger: Any) -> None:
    """每 60 秒回收一次：stale 标记 + 空闲 Router 退出。异常只告警，不退出循环。"""
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await service.reap()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            warn = getattr(logger, "warning", None)
            if callable(warn):
                warn(f"DSH 任务回收失败: {exc}")


@plugin.on_load
async def _on_load(ctx: Any) -> None:
    config = _coerce_config(ctx.config)
    gateway = _host_service(ctx, "dsh_gateway")
    router_mode = _host_service(ctx, "router_mode")
    hub = _host_service(ctx, "notification_hub")
    store = TaskStore(Path(ctx.data_dir) / "tasks.json", logger=ctx.logger)
    service = DshRouterService(
        config=config,
        store=store,
        logger=ctx.logger,
        gateway=gateway,
        router_mode=router_mode,
        notification_hub=hub,
    )
    state.ctx = ctx
    state.config = config
    state.service = service
    state.gateway = gateway
    state.router_mode = router_mode
    tools.bind_service(service)

    if gateway is not None:
        gateway.register_handler(ctx.plugin_name, service)
    if router_mode is not None:
        router_mode.set_context_provider(service.task_table)
        _bind_required_skills(router_mode, (ctx.plugin_name,), ctx.logger)

    from .commands import register_commands

    registered = register_commands(ctx, service)
    ctx.logger.info(
        f"{ctx.plugin_name} 已加载：工作区 {len(config.workspaces)} 个，"
        f"网关={'可用' if gateway is not None else '缺失'}，"
        f"Router={'可用' if router_mode is not None else '缺失'}，命令 {registered} 条"
    )


@plugin.on_startup
async def _on_startup(ctx: Any) -> None:
    service = state.service
    if service is None:
        return
    if state.heartbeat is not None and not state.heartbeat.done():
        return
    state.heartbeat = asyncio.create_task(
        _heartbeat_loop(service, getattr(ctx, "logger", None)),
        name="dsh_router_reap",
    )
    ctx.logger.info(f"{ctx.plugin_name} 已启动，每 {HEARTBEAT_SECONDS:g}s 回收一次任务状态")


@plugin.on_shutdown
async def _on_shutdown(ctx: Any) -> None:
    task, state.heartbeat = state.heartbeat, None
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # 协程内部已兜底，这里只防御
            ctx.logger.warning(f"DSH 回收协程退出异常: {exc}")
    if state.gateway is not None:
        try:
            state.gateway.unregister_handler(ctx.plugin_name)
        except Exception as exc:
            ctx.logger.warning(f"注销 DSH 网关 handler 失败: {exc}")
    if state.router_mode is not None:
        try:
            state.router_mode.set_context_provider(None)
        except Exception as exc:
            ctx.logger.warning(f"清除 Router 任务表 provider 失败: {exc}")
        _bind_required_skills(state.router_mode, (), ctx.logger)
    tools.bind_service(None)
    state.service = None
    state.ctx = None
    ctx.logger.info(f"{ctx.plugin_name} 已停止")


__all__ = [
    "HEARTBEAT_SECONDS",
    "PLUGIN_DESCRIPTION",
    "PLUGIN_VERSION",
    "PluginState",
    "plugin",
    "state",
]
