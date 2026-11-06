"""提示词构建上下文。

一次构建所需的全部输入集中在这里：配置、分区存储、会话作用域、占位符取值、
能力开关与运行时动态内容。注册表（blocks.py）与组合器（composer.py）只通过它
读值，不再各自 getattr(config, ...)。

约定：dynamic 里以 ``_`` 开头的键是内部控制位（如 ``_event``），不参与占位符渲染。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:  # 仅类型引用，避免 store <-> context <-> blocks 的循环导入
    from neobot_app.prompt.store import PromptStore


class Scope(str, Enum):
    """提示词作用域：群聊 / 私聊 / 直播间 / 子 Agent。"""

    GROUP = "group"
    PRIVATE = "private"
    LIVE = "live"
    SUBAGENT = "subagent"


BOTH_CHATS = frozenset({Scope.GROUP, Scope.PRIVATE})


@dataclass
class PromptContext:
    """一次提示词构建的输入与取值。

    字段可写，但组合器内部的临时改写（例如去重时把已消费的占位符置空）使用
    ``dataclasses.replace`` 生成副本，不污染调用方。
    """

    config: Any = None
    store: "PromptStore | None" = None
    scope: Scope = Scope.GROUP
    values: dict[str, Any] = field(default_factory=dict)
    features: dict[str, bool] = field(default_factory=dict)
    dynamic: dict[str, Any] = field(default_factory=dict)
    logger: Logger = field(default_factory=NullLogger)

    # ── 分区读写 ──

    def enabled(self, section: str, default: bool = True) -> bool:
        """分区是否启用（分区内 ``enabled = false`` 可关闭）。"""
        if self.store is None:
            return default
        return self.store.enabled(section, default=default)

    def raw_template(self, section: str, key: str = "template") -> str:
        """读取分区模板：文件（自定义覆盖默认）→ 内置兜底。

        store 不可用（面板/测试替身）时直接读随包分发的内置模板，保证注册表
        里的块仍按默认文案渲染，而不是整段消失。
        """
        from neobot_app.prompt.store import get_template_value, packaged_template

        if self.store is None:
            return packaged_template(section, key)
        return get_template_value(self.store, section, key)

    def render(self, section: str, key: str = "template") -> str:
        """渲染分区模板；空模板/全部占位符缺失时返回空串。"""
        from neobot_app.prompt.render import render_template

        return render_template(self.raw_template(section, key), self.render_values())

    # ── 条件与取值 ──

    def has_feature(self, name: str) -> bool:
        return bool(self.features.get(name))

    def dynamic_value(self, name: str, default: Any = None) -> Any:
        return self.dynamic.get(name, default)

    def render_values(self) -> dict[str, Any]:
        """占位符取值 = 静态 values + 动态内容（跳过 ``_`` 内部键）。"""
        values = dict(self.values)
        for key, value in self.dynamic.items():
            if isinstance(key, str) and key.startswith("_"):
                continue
            values[key] = value
        return values
