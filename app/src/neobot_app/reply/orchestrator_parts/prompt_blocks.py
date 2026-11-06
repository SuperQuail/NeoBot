"""提示词片段：运行时 user 块（时间 / 防重复 / 沉默提醒 / 等待指引）与技能渲染。

块的**文本/顺序/启停**由 ``prompt/blocks.py`` + ``prompt/composer.py`` 决定，
本模块只保留：
- 与回复循环强相关的**策略**（沉默提醒的轮次/时间阈值、被 @ 的判定）；
- 对组合器的薄封装（保持 orchestrator 侧的方法名稳定）。

历史上这里有一份 ``getattr(builder, ...)`` 的兼容回退，与 builder 各实现一遍渲染；
现在统一走组合器，回退分支已删除。
"""

from __future__ import annotations

from typing import Any

from neobot_app.prompt.composer import PromptComposer, make_context
from neobot_app.prompt.labels import render_label
from neobot_app.prompt.context import Scope
from neobot_app.time_context import get_current_time_values
from neobot_app.reply.event import ReplyEvent
from ._runtime import monotonic_seconds


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class PromptBlocksMixin:
    # ── 组合器接入 ──

    def _prompt_composer_service(self) -> PromptComposer:
        """惰性取得组合器（orchestrator 已持有 prompt_store/logger）。"""
        composer = getattr(self, "_prompt_composer", None)
        if composer is None:
            composer = PromptComposer(
                getattr(self, "_prompt_store", None),
                getattr(self, "_logger", None),
            )
            self._prompt_composer = composer
        return composer

    def _prompt_template(self, key: str, sub: str = "template") -> str:
        """读取提示词分区模板:文件(自定义覆盖默认) -> 内置兜底。"""
        from neobot_app.prompt.store import get_template_value

        return get_template_value(getattr(self, "_prompt_store", None), key, sub)

    def _prompt_section_enabled(self, key: str, default: bool = True) -> bool:
        store = getattr(self, "_prompt_store", None)
        if store is None:
            return default
        return store.enabled(key, default=default)

    def _runtime_ctx(self, *, scope: Scope = Scope.GROUP, dynamic: dict[str, Any] | None = None):
        return make_context(
            config=getattr(self, "_config", None),
            store=getattr(self, "_prompt_store", None),
            scope=scope,
            values=dict(get_current_time_values()),
            dynamic=dynamic,
            logger=getattr(self, "_logger", None),
        )

    # ── 运行时注入（阶段顺序由组合器保证） ──

    def _inject_runtime_blocks(
        self,
        messages: list[dict],
        *,
        dynamic: dict[str, Any] | None = None,
        state: Any = None,
    ) -> tuple[str, ...]:
        """按 RUNTIME_DATA → REMINDER → TIME 注入；返回本次实际渲染的块 id。"""
        ctx = self._runtime_ctx(dynamic=dynamic)
        self._prompt_composer_service().inject(messages, ctx, state)
        return tuple(getattr(state, "last_rendered", ())) if state is not None else ()

    def _append_block(
        self,
        messages: list[dict],
        block_id: str,
        *,
        dynamic: dict[str, Any] | None = None,
    ) -> bool:
        """按 id 追加单个块（循环中途的单条提醒），不参与阶段排序。"""
        ctx = self._runtime_ctx(dynamic=dynamic)
        return self._prompt_composer_service().append_block(messages, block_id, ctx)

    def _time_variant(self, full_sent: bool) -> str:
        """时间块变体：首次完整；之后短块（短块分区关闭或模板缺失时回退完整）。"""
        if not full_sent:
            return "full"
        if self._prompt_section_enabled("current_time_short") and self._prompt_template("current_time_short"):
            return "short"
        return "full"

    # ── 运行时 user 块 ──

    def _at_mention_wait_message(self, event: ReplyEvent) -> dict[str, str] | None:
        """被 @ 触发的那一轮追加的等待指引；其余情况返回 None。

        分工：[at_mention_wait] 与 chat.at_mention_reply_delay_seconds 是同一件事的两半 ——
        本体延迟默认已关（0，被 @ 立即回复），「要不要等对方补充」交给模型自己判断：
        对方没说要我做什么才 wait 五秒。
        走 user 块而不是 system 前缀：它只在本轮出现，混进 system 会让那段稳定前缀
        不再逐字节相同，白白丢掉上下文缓存。
        """
        if event.conversation_ref is None or event.conversation_ref.kind != "group":
            return None
        willing = getattr(self, "_willing_service", None)
        message = event.message
        if willing is None or message is None:
            return None
        try:
            mentioned = bool(willing.is_at_mentioned(message))
        except Exception:
            return None
        if not mentioned:
            return None
        ctx = self._runtime_ctx(dynamic={"at_mention_wait": True})
        return self._prompt_composer_service().build_user_block("at_mention_wait", ctx)

    # ── 沉默提醒（策略 + 文本） ──

    def _nudge_reason(
        self,
        *,
        reply_sent: bool,
        rounds: int,
        next_at: int,
        emitted: int,
        deadline: float,
    ) -> str | None:
        """判断此刻是否需要注入沉默提醒。

        满足轮次或时间任一触发条件时返回原因("rounds" / "seconds"),否则返回 None。
        时间用 monotonic_seconds(),与 120s 活动看门狗语义不同(后者测"两次活动之间的空档")。
        """
        enabled, first_rounds, _repeat_rounds, seconds, max_emitted = self._get_silent_nudge_settings()
        if not enabled or emitted >= max_emitted or reply_sent:
            return None
        if not self._prompt_section_enabled("silent_nudge"):
            # 分区被关闭时既不注入也不刷新记录器,行为回到现状
            return None
        if first_rounds > 0 and rounds >= next_at:
            return "rounds"
        if seconds > 0 and monotonic_seconds() >= deadline:
            return "seconds"
        return None

    def _should_nudge(
        self,
        *,
        reply_sent: bool,
        rounds: int,
        next_at: int,
        emitted: int,
        deadline: float,
    ) -> bool:
        """是否需要注入沉默提醒(_nudge_reason 的布尔形式)。"""
        return (
            self._nudge_reason(
                reply_sent=reply_sent,
                rounds=rounds,
                next_at=next_at,
                emitted=emitted,
                deadline=deadline,
            )
            is not None
        )

    # ── 技能 / 恢复块 ──

    @staticmethod
    def _render_skills(skills: list[Any]) -> str:
        lines: list[str] = []
        for skill in skills:
            skill_id = getattr(skill, "qualified_name", None) or skill.name
            description = getattr(skill, "description", "") or ""
            lines.append(
                render_label(
                    "skills",
                    "item",
                    '<skill id="{skill_id}" description="{description}" />',
                    skill_id=_xml_escape(str(skill_id)),
                    description=_xml_escape(str(description)),
                )
            )
        return "\n".join(lines)

    def _render_resume_context(self, new_member_text: str) -> str:
        """渲染群聊挂起恢复的说明文本(模板来自 [group_chat_resume])。"""
        builder = getattr(self, "_prompt_builder", None)
        render = getattr(builder, "build_group_chat_resume_text", None)
        if callable(render):
            return render(new_member_profiles=new_member_text)
        template = self._prompt_template("group_chat_resume")
        values = get_current_time_values()
        values["new_member_profiles"] = new_member_text
        from neobot_app.prompt.render import render_template

        return render_template(template, values)
