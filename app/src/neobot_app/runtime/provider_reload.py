"""模型 / API Key 变更后的 provider 重建消费者。

模型名、平台密钥都固化在 provider 实例里，改配置后必须重建才能生效。重建的
难点是「谁持有旧 provider」——这里把持有者收敛成三个稳定的挂载点
（回复编排器、图片解析、档案总结），并由它们各自的 install_* 方法做原子换引用。

设计约束：
- 只换引用、**不关闭旧 provider**：全部替换成功后才统一关闭，避免中途失败时
  旧 provider 已被关闭导致服务不可用；
- 新 provider 建不起来时整体放弃，旧 provider 继续服务（宁可保持可用，
  也不要变成「配错一次就彻底不回复」）；
- 依赖注入装配器（builder）与卸载器（disposer），本模块不 import 任何具体
  Provider 实现，依赖方向保持在 app 侧向下。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.runtime.hot_reload_registry import ConfigConsumer


@dataclass(frozen=True, slots=True)
class ProviderBundle:
    """一次重建产出的 provider 组合。"""

    main: Any = None
    main_error: str | None = None
    vision: Any = None


class ProviderReloadConsumer(ConfigConsumer):
    """模型与平台密钥变更时重建 provider 并原地替换。"""

    config_paths: tuple[str, ...] = ("models",)

    def __init__(
        self,
        *,
        builder: Callable[[Any], ProviderBundle],
        installers: dict[str, tuple[Callable[[ProviderBundle], Any], Callable[[Any], Any]]],
        logger: Logger | None = None,
    ) -> None:
        """Args:
        builder: ``(config) -> ProviderBundle``，用新配置构建 provider。
        installers: 挂载点名称 -> (安装函数, 拆卸函数)：

            - 安装函数 ``(bundle) -> 被替换下来的旧对象``：自己从 bundle 里取
              需要的 provider，并原子换引用；
            - 拆卸函数 ``(旧对象) -> None | Awaitable``：负责关闭旧 provider。

            挂载点由组合根决定，本模块不认识任何具体服务。
        """
        self._builder = builder
        self._installers = installers
        self._logger = logger or NullLogger()

    @property
    def name(self) -> str:
        return "provider"

    @property
    def hot_reload_policies(self) -> tuple[Any, ...]:
        from neobot_app.config.hot_reload import HotReloadRule

        return (
            HotReloadRule(
                "models",
                True,
                "模型库与平台密钥变更后重建 provider 并原地替换（新 provider 不可用时保持原样）",
            ),
        )

    async def apply_config(self, config: Any) -> None:
        bundle = self._builder(config)
        if bundle.main is None:
            # 新配置下主模型不可用：保留现状比换成「不会回复」更安全。
            raise RuntimeError(
                f"新配置下主回复模型不可用，已保留原 provider：{bundle.main_error or '原因未知'}"
            )

        replaced: list[tuple[str, Callable[[Any], Any], Any]] = []
        try:
            for label, (install, dispose) in self._installers.items():
                previous = install(bundle)
                replaced.append((label, dispose, previous))
        except Exception:
            # 安装失败：已换上的不回滚（可能已进入使用），但绝不关闭任何旧
            # provider —— 让它们随进程结束回收，好过留下悬空引用。
            self._logger.error("provider 替换失败，旧 provider 保持未关闭")
            raise

        for label, dispose, previous in replaced:
            await self._dispose(label=label, dispose=dispose, previous=previous)
        self._logger.info(
            "provider 已按新配置重建",
            model=getattr(bundle.main, "model", "") or "",
            vision_model=getattr(bundle.vision, "model", "") or "",
        )

    # ── 内部 ────────────────────────────────────────────────────────

    async def _dispose(
        self,
        *,
        label: str,
        dispose: Callable[[Any], Any],
        previous: Any,
    ) -> None:
        if previous is None:
            return
        try:
            result = dispose(previous)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            self._logger.warning(
                f"旧 provider 释放失败（忽略）: {label}",
                error_type=type(exc).__name__,
                error=str(exc),
            )
