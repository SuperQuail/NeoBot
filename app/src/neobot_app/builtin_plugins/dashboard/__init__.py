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
from .metrics import latency_sample_capacity
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

#: 探针启动前的预热时间（秒）：避开启动高峰，等插件与适配器就绪
PROBE_WARMUP_SECONDS = 3.0


class DashboardPlugin:
    """面板插件运行时状态。"""

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: DashboardConfig | None = None
        self.server: DashboardServer | None = None
        self._latency_task: asyncio.Task[None] | None = None
        #: 探针状态迁移去重（"" / "probing" / "idle" / "disabled"）
        self._probe_state: str = ""
        self._logger: Any = None
        #: 插件配置的「原地生效」消费者（bugfixes/feat(2) §6）
        self._config_consumer: Any = None

    # ------------------------------------------------------------------

    async def load(self, ctx: Any) -> None:
        self.ctx = ctx
        self._logger = getattr(ctx, "logger", None)
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

        self._register_config_consumer(ctx)
        await self._start_latency_task()

    def _register_config_consumer(self, ctx: Any) -> None:
        """把自己登记成 modloader 的「插件配置消费者」。

        登记后，面板里保存 latency_probe_* / bot_info_cache_ttl / log_buffer_size 等
        运行期安全字段会**立即生效**，不再提示「需要重启 NeoBot」；
        host / port / base_path 与安全类字段仍按需要重启处理。
        未登记（宿主机旧版本）时行为完全不变。
        """
        control = getattr(ctx, "plugin_control", None)
        register = getattr(control, "register_config_consumer", None)
        if not callable(register):
            return
        try:
            from .hot_reload import DashboardConfigConsumer

            self._config_consumer = DashboardConfigConsumer(self)
            register(ctx.plugin_name, self._config_consumer)
        except Exception as exc:  # 登记失败不能影响面板启动
            self._config_consumer = None
            if self._logger is not None:
                self._logger.warning(f"面板配置热重载通道登记失败: {exc}")

    def apply_runtime_config(self, config: DashboardConfig) -> None:
        """把运行期安全的配置字段原地生效（供配置消费者调用）。

        失败时向上抛出，让调用方保留旧配置并把错误报给面板。
        """
        server = self.server
        if server is not None:
            server.apply_runtime_config(config)
        self.config = config

    async def _start_latency_task(self) -> None:
        """（重新）启动探针任务：先取消旧的，保证同一时刻只有一个在跑。"""
        await self._cancel_latency_task()
        self._probe_state = ""
        self._latency_task = asyncio.create_task(self._latency_loop())

    async def _cancel_latency_task(self) -> None:
        """取消并回收当前的探针任务（幂等，可在 load()/unload() 里安全调用）。"""
        task = self._latency_task
        self._latency_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def unload(self) -> None:
        # 先注销配置消费者：它持有本实例的引用，留着会被喂给已释放的对象
        control = getattr(self.ctx, "plugin_control", None)
        unregister = getattr(control, "unregister_config_consumer", None)
        if self._config_consumer is not None and callable(unregister):
            try:
                unregister(getattr(self.ctx, "plugin_name", "dashboard"))
            except Exception:
                pass
        self._config_consumer = None

        await self._cancel_latency_task()
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

    def _log_probe_state(self, state: str, **fields: Any) -> None:
        """探针状态迁移日志：同一状态只记一次（启动 / 恢复探测 / 进入空闲停止 / 关闭）。"""
        if state == self._probe_state:
            return
        self._probe_state = state
        logger = self._logger
        if logger is None:
            return
        detail = " ".join(f"{key}={value}" for key, value in fields.items())
        try:
            if state == "probing":
                logger.info(f"面板延迟探针已启动/恢复探测: {detail}")
            elif state == "idle":
                logger.info(f"面板延迟探针进入空闲停止（窗口内无活跃会话）: {detail}")
            elif state == "disabled":
                logger.info(f"面板延迟探针已关闭（latency_probe_interval_seconds=0）: {detail}")
        except Exception:
            pass

    async def _latency_loop(self) -> None:
        """面板延迟探针（带会话门控 + 空闲完全停止）。

        实现前请先读完这三条约束：

        1. **只有「配置明确关闭（interval <= 0）」或「插件卸载（server is None）」才退出循环。**
        2. **空闲期（idle=0）必须继续存活**，只做一次廉价的门控复检（不产生 API 调用）。
           若照搬"空闲即 return"，由于本任务只在 load() 创建一次、而 dashboard 声明
           hot_reload=False 导致 load() 不会重跑，探针会**永久停摆**、再也无法恢复。
        3. 门控只读会话的 last_seen_at（SessionStore.has_recent_activity），
           绝不能走 SessionStore.get() —— 那会 touch() 会话造成自我续期。
        """
        await asyncio.sleep(PROBE_WARMUP_SECONDS)
        while True:
            server = self.server
            config = self.config
            if server is None or config is None:
                return

            active_interval = float(config.latency_probe_interval_seconds or 0)
            if active_interval <= 0:
                self._log_probe_state("disabled", interval=active_interval)
                return  # 用户明确关闭探针

            idle_interval = float(config.latency_probe_idle_seconds or 0)
            # 下限取 0.05s：真实配置项本身有 ge=1 约束，这里只是为了让单测可以快速驱动循环
            gate_interval = max(0.05, float(config.latency_probe_gate_check_seconds or 30))
            window = float(config.latency_probe_active_window_seconds or 120)

            sessions = getattr(server, "sessions", None)
            active = bool(
                sessions is not None
                and sessions.has_recent_activity(window)
            )
            delay = active_interval if active else idle_interval
            # 让面板按「实际采样间隔」判断样本是否陈旧，并据此刷新样本容量（配置可热更新）
            effective_interval = delay if delay > 0 else active_interval
            try:
                server.metrics.set_latency_stale_after(effective_interval * 5.0)
                server.metrics.set_latency_capacity(
                    latency_sample_capacity(effective_interval)
                )
            except Exception:
                pass

            try:
                if delay > 0:
                    self._log_probe_state(
                        "probing", interval=delay, active=active, window=window
                    )
                    await server.probe_latency()
                    await asyncio.sleep(delay)
                else:
                    # 空闲且 idle=0：不探测、不写指标，只做一次廉价的门控复检
                    self._log_probe_state(
                        "idle", gate_check=gate_interval, window=window
                    )
                    await asyncio.sleep(gate_interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 单次探测异常不应终止循环；退避一个周期后继续
                await asyncio.sleep(max(0.05, delay if delay > 0 else gate_interval))


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
