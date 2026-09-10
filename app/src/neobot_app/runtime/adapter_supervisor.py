"""适配器生命周期与配置变更的唯一负责人。

为什么需要这一层：`AdapterCore` 已经同时负责 WS 服务、握手鉴权、连接集合、
消息队列、心跳与 echo 关联六件事。把「运行期改监听设置」也塞进去就是第七件
职责，而且它必须知道接收线程的启停细节。这些编排（何时停、何时重启、失败
如何回滚）属于控制面，不属于适配器内核。

为什么不能「重建 adapter 对象」：适配器实例被技能、表情包服务、文件服务、
命令服务等几十处直接持有引用。换对象等于全量重新装配。因此这里改的是适配器
内部的监听设置，对象身份保持不变，所有既有引用自动看到新值。

依赖方向：本模块位于 app 侧，只依赖 packages 暴露的 ``AdapterReconfigurable``
能力协议，不依赖任何具体适配器实现。
"""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.interfaces import AdapterReconfigurable

from neobot_app.config.hot_reload import HotReloadRule
from neobot_app.runtime.hot_reload_registry import ConfigConsumer


class AdapterSupervisor(ConfigConsumer):
    """按配置变更安全地重启反向 WebSocket 监听。"""

    #: 关心的配置前缀：适配器监听设置与机器人账号（账号影响适配器初始化）。
    config_paths: tuple[str, ...] = ("adapter",)

    #: 生效方式声明：已实现运行期重启监听，因此 adapter.* 不再是「需重启」。
    #: 面板自身的监听地址/端口不在这里 —— 面板归 dashboard 插件管，改动它们
    #: 需要重开面板的 HTTP 服务，仍按「需重启」处理。
    hot_reload_policies: tuple[HotReloadRule, ...] = (
        HotReloadRule(
            "adapter",
            True,
            "反向 WebSocket 监听设置在运行期按新配置重启（连接瞬断后由框架自动重连）",
        ),
    )

    def __init__(
        self,
        adapter: Any,
        *,
        logger: Logger | None = None,
        stop_timeout: float = 8.0,
    ) -> None:
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._stop_timeout = stop_timeout

    @property
    def name(self) -> str:
        return "adapter"

    @property
    def adapter(self) -> Any:
        return self._adapter

    @property
    def reconfigurable(self) -> bool:
        """当前适配器是否支持运行期改监听设置。

        能力查询走接口判断而非 hasattr 猜测：不支持改设置的适配器（如内嵌
        local 模式）会明确返回 False，而不是在运行期炸在某个属性上。
        """
        return isinstance(self._adapter, AdapterReconfigurable)

    # ── 配置生效 ────────────────────────────────────────────────────

    async def apply_config(self, config: Any) -> None:
        """配置热重载入口：解析新设置并按需重启监听。

        Raises:
            RuntimeError: 新设置与原设置不同，但适配器不支持运行期改设置。
            OSError: 新端口/地址无法绑定（旧设置已回滚并重新监听）。
        """
        settings = self._resolve_settings(config)
        if settings is None:
            return
        await self.reconfigure(settings)

    async def reconfigure(self, settings: Any) -> bool:
        """按新监听设置重启接收服务；失败则回滚到旧设置。

        Returns:
            True 表示当前正在使用新设置（含「本来就一致、无需重启」）。
        """
        if not self.reconfigurable:
            raise RuntimeError(
                "当前适配器不支持运行期修改监听设置；请在 config.toml 改好后重启 NeoBot"
            )
        previous = self._adapter.settings
        if previous == settings:
            self._logger.debug("适配器监听设置未变化，跳过重启")
            return True

        self._logger.warning(
            "适配器监听设置变更，正在重启反向 WebSocket 服务",
            before=previous.describe(),
            after=settings.describe(),
        )
        await self._restart_with(previous, settings)
        self._logger.info(f"适配器监听设置已生效: {settings.describe()}")
        return True

    def describe(self) -> dict[str, Any]:
        """当前监听与连接状态（供面板/日志展示）。"""
        try:
            settings = self._adapter.settings
            address = f"ws://{settings.host}:{settings.port}"
            token_enabled = bool(settings.token_enabled)
        except Exception:
            address = ""
            token_enabled = False
        return {
            "address": address,
            "token_enabled": token_enabled,
            "connected": bool(getattr(self._adapter, "connected", False)),
            "reconfigurable": self.reconfigurable,
        }

    # ── 内部 ────────────────────────────────────────────────────────

    def _resolve_settings(self, config: Any) -> Any | None:
        """从配置解析出监听设置；拿不到配置时返回 None（保持现状）。"""
        adapter_cfg = getattr(config, "adapter", None)
        if adapter_cfg is None:
            return None
        from neobot_adapter.onebot.receiver.settings import ReverseWsSettings

        return ReverseWsSettings.resolve(
            host=str(getattr(adapter_cfg, "reverse_ws_host", "") or "") or None,
            port=int(getattr(adapter_cfg, "reverse_ws_port", 0) or 0) or None,
            access_token=str(
                getattr(adapter_cfg, "reverse_ws_access_token", "") or ""
            ),
        )

    async def _restart_with(self, previous: Any, settings: Any) -> None:
        """停止 → 改设置 → 重启；任一步失败都回滚到 previous。"""
        await self._adapter.stop()
        self._adapter.reconfigure(settings)
        try:
            await self._adapter.start()
        except Exception as exc:
            self._logger.error(
                "新监听设置启动失败，回滚到原设置",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            self._adapter.reconfigure(previous)
            try:
                await self._adapter.start()
            except Exception as rollback_exc:
                self._logger.error(
                    "回滚后适配器仍未启动，反向 WebSocket 服务当前不可用",
                    error_type=type(rollback_exc).__name__,
                    error=str(rollback_exc),
                )
                raise
            raise
