"""提示词组合器：按注册表把块拼成 system 文本 / 上下文消息 / 运行时注入块。

组合器是**唯一**知道「块该放哪、按什么顺序、为什么跳过」的地方；builder 只负责
收集占位符取值，orchestrator 只负责驱动时机。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.prompt.blocks import (
    Block,
    Stage,
    block_by_id,
    blocks_for,
)
from neobot_app.prompt.context import PromptContext, Scope
from neobot_app.prompt.render import render_template, template_placeholders


@dataclass(frozen=True)
class SystemPrompt:
    """一次 system 提示词构建的结果（含构建元信息，便于调试/面板）。"""

    text: str
    consumed: frozenset[str] = frozenset()
    rendered: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ContextBuild:
    """一次上下文 user 块构建的结果。"""

    messages: tuple[dict[str, str], ...] = ()
    rendered: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


@dataclass
class RuntimeState:
    """注入管道的运行态：记录「每次激活只发一次」与最近一次注入结果。"""

    activation_emitted: set[str] = field(default_factory=set)
    last_rendered: tuple[str, ...] = ()


def _merge(*parts: str) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned)


#: system 已消费时、上下文块里应置空（去重）的占位符。只限这些历史契约键：
#: 其它占位符（bot_name/group_name…）在 context 里仍然是合法用法，不能一起清空。
_DEDUPE_KEYS_BY_SCOPE: dict[Scope, frozenset[str]] = {
    Scope.GROUP: frozenset(
        {
            "member_list",
            "key_word_reaction_list",
            "memory_list",
            "group_info",
            "group_admin",
            "bot_group_admin_status",
        }
    ),
    Scope.PRIVATE: frozenset(
        {
            "profile",
            "friend_info",
            "key_word_reaction_list",
            "memory_list",
        }
    ),
}


class PromptComposer:
    """按注册表组合提示词。"""

    def __init__(self, store: Any = None, logger: Logger | None = None) -> None:
        self._store = store
        self._logger = logger or NullLogger()

    # ── 底层：单块渲染 ──

    def block_skip_reason(self, block: Block, ctx: PromptContext) -> str | None:
        """块是否可以跳过：先查分区开关（主模板除外），再按声明顺序求值条件。"""
        section = block.template_section
        if section is not None and block.stage is not Stage.SYSTEM_MAIN and not ctx.enabled(section):
            return f"分区 [{section}] 已关闭"
        for check in block.requires:
            reason = check(ctx)
            if reason:
                return reason
        return None

    def render_block(self, block: Block, ctx: PromptContext) -> str:
        """渲染单块文本；动态文本块走 ``text`` 提供者，模板块走 TOML 分区。"""
        if block.text is not None:
            return str(block.text(ctx) or "").strip()
        section = block.template_section
        if section is None:
            return ""
        return ctx.render(section, block.key)

    @staticmethod
    def _consumed_placeholders(block: Block, ctx: PromptContext) -> set[str]:
        section = block.template_section
        if section is None:
            return set()
        return template_placeholders(ctx.raw_template(section, block.key))

    # ── system ──

    def _with_fragments(self, ctx: PromptContext) -> tuple[PromptContext, set[str]]:
        """把 FRAGMENT 块渲染成 ``{块id}`` 取值，供主模板等通过占位符引用。

        返回 (新 ctx, 片段模板占位符集合)。占位符集合并入 system 的 consumed，
        否则片段里用掉的 ``{member_list}`` 会在上下文块里重复渲染一次。

        片段不存在/被关闭时不给值：模板里的占位符保持原样（或整段覆盖的旧自定义
        不含占位符时自然不会插入），避免重复。
        """
        values = dict(ctx.values)
        fragment_placeholders: set[str] = set()
        for block in blocks_for(Stage.FRAGMENT, ctx.scope):
            section = block.template_section
            if section is None:
                continue
            text = ""
            if not self.block_skip_reason(block, ctx):
                text = self.render_block(block, ctx)
            # 关闭/为空也显式给空值：主模板里的 {块id} 否则会以字面量泄漏进 system
            values[block.id] = text
            if text:
                fragment_placeholders |= template_placeholders(ctx.raw_template(section, block.key))
        if values == ctx.values:
            return ctx, fragment_placeholders
        return replace(ctx, values=values), fragment_placeholders

    def fragment(self, block_id: str, ctx: PromptContext) -> str:
        """读取一个 FRAGMENT 块的渲染结果（不存在/关闭/为空时返回空串）。"""
        block = block_by_id(block_id)
        if block.template_section is None or self.block_skip_reason(block, ctx):
            return ""
        return self.render_block(block, ctx)

    def build_system(self, ctx: PromptContext) -> SystemPrompt:
        """拼 system：cot 前缀 → 主模板 → 末尾追加。"""
        ctx, fragment_placeholders = self._with_fragments(ctx)
        rendered: list[str] = []
        skipped: list[tuple[str, str]] = []
        consumed: set[str] = set(fragment_placeholders)

        # 全局 cot 板块必须在最前面；各子块按 order 拼接后整体放在主模板之前。
        prefix_parts: list[str] = []
        for block in blocks_for(Stage.SYSTEM_PREFIX, ctx.scope):
            reason = self.block_skip_reason(block, ctx)
            if reason:
                skipped.append((block.id, reason))
                continue
            part = self.render_block(block, ctx)
            if not part:
                skipped.append((block.id, "渲染为空"))
                continue
            prefix_parts.append(part)
            consumed |= self._consumed_placeholders(block, ctx)
            rendered.append(block.id)

        main_parts: list[str] = []
        for block in blocks_for(Stage.SYSTEM_MAIN, ctx.scope):
            part = self.render_block(block, ctx)
            if not part:
                skipped.append((block.id, "模板为空"))
                continue
            main_parts.append(part)
            consumed |= self._consumed_placeholders(block, ctx)
            rendered.append(block.id)
        text = _merge(*prefix_parts, *main_parts)

        # 编号格式是给模型的固定约定：模板漏写时补回 system（与模板无关的兜底）
        guide = str(ctx.values.get("numbering_guide") or "").strip()
        if guide and "numbering_guide" not in consumed:
            text = _merge(text, f"<消息编号说明>\n{guide}\n</消息编号说明>")

        for block in blocks_for(Stage.SYSTEM_APPEND, ctx.scope):
            reason = self.block_skip_reason(block, ctx)
            if reason:
                skipped.append((block.id, reason))
                continue
            part = self.render_block(block, ctx)
            if not part:
                skipped.append((block.id, "渲染为空"))
                continue
            consumed |= self._consumed_placeholders(block, ctx)
            text = _merge(text, part)
            rendered.append(block.id)

        self._log_skipped(tuple(skipped))
        return SystemPrompt(
            text=text,
            consumed=frozenset(consumed),
            rendered=tuple(rendered),
            skipped=tuple(skipped),
        )

    def _log_skipped(self, skipped: tuple[tuple[str, str], ...]) -> None:
        """把被跳过的块与原因记入日志（线上排查「为什么没注入」）。"""
        if not skipped:
            return
        self._logger.debug(
            "提示词块已跳过",
            blocks=[{"id": block_id, "reason": reason} for block_id, reason in skipped],
        )

    # ── 上下文 user 块 ──

    def build_context(self, ctx: PromptContext, system: SystemPrompt | None = None) -> ContextBuild:
        """渲染 CONTEXT 阶段块；system 已消费的**去重键**自动置空。"""
        if system is not None and system.consumed:
            dedupe_keys = _DEDUPE_KEYS_BY_SCOPE.get(ctx.scope, frozenset())
            blanked = system.consumed & dedupe_keys
            if blanked:
                values = dict(ctx.values)
                for key in blanked:
                    values[key] = ""
                ctx = replace(ctx, values=values)
        messages: list[dict[str, str]] = []
        rendered: list[str] = []
        skipped: list[tuple[str, str]] = []
        for block in blocks_for(Stage.CONTEXT, ctx.scope):
            reason = self.block_skip_reason(block, ctx)
            if reason:
                skipped.append((block.id, reason))
                continue
            part = self.render_block(block, ctx)
            if not part:
                skipped.append((block.id, "渲染为空"))
                continue
            messages.append({"role": "user", "content": part})
            rendered.append(block.id)
        return ContextBuild(
            messages=tuple(messages),
            rendered=tuple(rendered),
            skipped=tuple(skipped),
        )

    def build_context_messages(self, ctx: PromptContext, system: SystemPrompt | None = None) -> list[dict[str, str]]:
        """``build_context`` 的便捷形式，只要消息列表。"""
        return list(self.build_context(ctx, system).messages)

    # ── 运行时注入（RUNTIME_DATA / REMINDER / TIME） ──

    def inject(
        self,
        messages: list[dict],
        ctx: PromptContext,
        state: RuntimeState | None = None,
    ) -> list[dict]:
        """按阶段顺序追加运行时块；TIME 阶段块保证位于消息末尾。

        ``state.activation_emitted`` 用于 ``once_per_activation`` 块：已发过的块
        本次激活内不再发。
        """
        state = state or RuntimeState()
        rendered: list[str] = []
        terminals: list[dict] = []
        for stage in (Stage.RUNTIME_DATA, Stage.REMINDER, Stage.TIME):
            for block in blocks_for(stage, ctx.scope):
                if block.once_per_activation and block.id in state.activation_emitted:
                    continue
                reason = self.block_skip_reason(block, ctx)
                if reason:
                    continue
                part = self.render_block(block, ctx)
                if not part:
                    continue
                message = {"role": "user", "content": part}
                messages.append(message)
                rendered.append(block.id)
                if block.once_per_activation:
                    state.activation_emitted.add(block.id)
                if block.terminal:
                    terminals.append(message)
        # terminal 块必须是请求的最后一条；即使未来有块追加在它之后也在这里纠正
        for message in terminals:
            if messages and messages[-1] is message:
                continue
            messages.remove(message)
            messages.append(message)
        state.last_rendered = tuple(rendered)
        return messages

    def append_block(self, messages: list[dict], block_id: str, ctx: PromptContext) -> bool:
        """按 id 追加单个块（不参与阶段排序）；用于循环中途的单条提醒。"""
        block = block_by_id(block_id)
        if self.block_skip_reason(block, ctx):
            return False
        part = self.render_block(block, ctx)
        if not part:
            return False
        messages.append({"role": "user", "content": part})
        return True

    # ── 状态 / 子 Agent 文案 ──

    def render_status_text(self, block_id: str, ctx: PromptContext) -> str:
        """按块 id 渲染状态文案（sleep / wake / 兜底等）；条件不满足返回空串。"""
        block = block_by_id(block_id)
        if self.block_skip_reason(block, ctx):
            return ""
        return self.render_block(block, ctx)

    def render_section(self, section: str, ctx: PromptContext, key: str = "template") -> str:
        """直接渲染任意 TOML 分区（子 Agent、直播等不走管道的场景）。"""
        return render_template(ctx.raw_template(section, key), ctx.render_values())

    def build_user_block(self, block_id: str, ctx: PromptContext) -> dict[str, str] | None:
        """渲染一个 user 消息块；条件不满足或为空时返回 None。"""
        text = self.render_status_text(block_id, ctx)
        return {"role": "user", "content": text} if text else None


def make_context(
    *,
    config: Any = None,
    store: Any = None,
    scope: Scope = Scope.GROUP,
    values: dict[str, Any] | None = None,
    features: dict[str, bool] | None = None,
    dynamic: dict[str, Any] | None = None,
    logger: Logger | None = None,
) -> PromptContext:
    """构造 PromptContext 的便捷函数（调用方少写样板）。"""
    return PromptContext(
        config=config,
        store=store,
        scope=scope,
        values=dict(values or {}),
        features=dict(features or {}),
        dynamic=dict(dynamic or {}),
        logger=logger or NullLogger(),
    )
