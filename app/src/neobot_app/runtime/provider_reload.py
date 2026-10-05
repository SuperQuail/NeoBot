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
    """模型与平台密钥变更时重建 provider 并原地替换。

    `env` 与 `models` 并列在关心范围内：平台 URL / APIKey 来自 `.env`，
    **不进 config.toml 的配置快照**，所以「只改环境变量」不会体现在配置 diff 里。
    面板保存 env 时会显式带上这条路径（`dashboard/api.py` 的 `env_save`），
    否则消费者根本不会被触发，新凭据要等重启才生效（issue #74）。
    """

    config_paths: tuple[str, ...] = ("models", "env")

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
            HotReloadRule(
                "env",
                True,
                "平台凭据（.env）变更后重建 provider；覆盖 主对话 / 视觉 / 档案总结 三个挂载点",
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


class ModelConsumerReload(ConfigConsumer):
    """通用「持有模型产物的组件」重建器：接入一行，失败互不牵连。

    为什么需要它：provider 之外还有组件把**模型条目**固化在自己身上 ——
    TTS 服务（音色与平台密钥）、生图服务（默认模型与平台）、可选 Agent 的 provider。
    它们此前只在启动期装配一次，于是「先在面板里配好平台 Key，再重载」走不通，
    必须重启进程。

    与 `ProviderReloadConsumer` 的分工：那个负责「主对话 / 视觉 / 档案总结」这一组
    **共享 bundle、原子换装**的 provider；这个负责其余**各自独立**的组件 ——
    每个组件注册成独立消费者，注册表本就是「单个失败不影响其余组件」
    （`hot_reload_registry.apply`），所以 TTS 建不起来不会拖垮 provider 的重建，
    报告里也能逐个看到成败。

    接入方式（装配处一行）：

        registry.register(ModelConsumerReload(name="tts", rebuild=_rebuild_tts))
    """

    def __init__(
        self,
        *,
        name: str,
        rebuild: Callable[[Any], Any],
        reason: str = "",
        logger: Logger | None = None,
    ) -> None:
        self._name = name
        self._rebuild = rebuild
        self._reason = reason or f"{name} 持有的模型配置变更后重建"
        self._logger = logger or NullLogger()

    #: 与 provider 消费者同源：模型库与平台凭据（.env）变了都要重建。
    config_paths: tuple[str, ...] = ("models", "env")

    @property
    def name(self) -> str:
        return self._name

    @property
    def hot_reload_policies(self) -> tuple[Any, ...]:
        from neobot_app.config.hot_reload import HotReloadRule

        return (
            HotReloadRule("models", True, self._reason),
            HotReloadRule("env", True, self._reason),
        )

    async def apply_config(self, config: Any) -> None:
        """重建并换装。失败直接抛出：由注册表记为「该组件失败」，其余组件继续。"""
        result = self._rebuild(config)
        if inspect.isawaitable(result):
            await result
        self._logger.info(f"{self._name} 已按新配置重建")


#: 模型 / 凭据变更后**已知仍未接入热重载**的部分（issue #75）。
#:
#: 为什么要显式列出来：`models` 在分类表里是「可热重载」，于是 `needs_restart_count` 恒为 0，
#: 面板只会说「全部已生效」。缺口摆在这里保持可见：**补齐一个就删一条**，删空后提示自然消失。
#:
#: 2026-10 审计（issue #75）后为空，逐条结论：
#: - 表情包图片解析、技能（绘图看参考图 / 图片解析）：**已接入**换装入口并注册消费者
#: - `drawing/service.py` 的 `_vision_provider` 属于 `CreatorImageService` ——
#:   它已被 `creator_image` 消费者**整体重建**，不是缺口
#: - `runtime/application.py` 的引用只用于 `close()`（资源清理），与「用哪个模型」无关
#: - `reply/sender.py` 的 `_provider` 赋值后**从未被读取**（死状态）
#: - `reply/tools.py` 的 `ReplyToolExecutor` 由 `build_reply_toolset` **每回复**构建，
#:   传的是编排器当前 provider（`native_vision_provider=self._provider`），天然跟得上
#:
#: 遗留（非 staleness，但值得知道）：服务注册表里的 `services["vision_provider"]` 仍是
#: 启动期实例（仓库内无消费者）；插件若读取它，换模型后要自行重新取。
MODEL_RELOAD_GAPS: tuple[str, ...] = ()


def model_reload_restart_hint() -> str:
    """模型 / 凭据变更后追加的「仍需重启」提示；缺口清空时返回空串。"""
    if not MODEL_RELOAD_GAPS:
        return ""
    return (
        "；以下部分仍需**重启进程**后才会用新模型："
        + "、".join(MODEL_RELOAD_GAPS)
    )
