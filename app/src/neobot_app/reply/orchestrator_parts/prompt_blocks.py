"""提示词片段：时间块、防重复、沉默提醒、技能渲染。"""
from __future__ import annotations

from typing import Any
from neobot_app.prompt.render import render_template
from neobot_app.prompt.store import get_template_value
from neobot_app.reply.event import ReplyEvent
from neobot_app.time_context import get_current_time_values
from ._runtime import monotonic_seconds

def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
#: 被 @ 的触发消息优先级提示；只在该轮触发消息确实 @ 了 bot 时注入。
_AT_MENTION_PRIORITY_BLOCK = "<@>这是@你的消息,你应该优先回复<@>"
_NO_TOOL_CALL_REMINDER = (
    "系统提醒：你刚才没有调用任何工具。"
    "如果你确认不需要回复或执行任何操作，请调用 cancel 工具结束；"
    "如果需要回复用户，请调用 send_reply 工具发送回复。"
    "不要只输出正文草稿，也不要重复分析。"
)
#: [silent_nudge] 分区缺失时的内置兜底文本（与 templates/prompts.toml 的定稿逐字一致）。
_SILENT_NUDGE_TEXT = (
    "[系统提示] 请检查是否有必要使用回复工具告知其他人你的工作进度."
    "不使用send_reply的情况下他们不知道你做了什么."
)

class PromptBlocksMixin:
    def _prompt_template(self, key: str, sub: str = "template") -> str:
        """读取提示词分区模板:文件(自定义覆盖默认) -> 内置兜底。"""
        return get_template_value(self._prompt_store, key, sub)
    def _prompt_section_enabled(self, key: str, default: bool = True) -> bool:
        if self._prompt_store is None:
            return default
        return self._prompt_store.enabled(key, default=default)
    def _native_vision_note(self) -> str:
        """原生视觉说明([native_vision] 模板);分区关闭或模板为空时返回空串。

        这段说明是**稳定内容**,因此追加在 system 提示词里而不是对话末尾:
        系统提示词在各条管线之间逐字节相同,能持续命中上下文缓存;
        追加在历史之后的位置随历史长度变化,永远无法进入可复用前缀。
        """
        if not self._prompt_section_enabled("native_vision"):
            return ""
        return render_template(self._prompt_template("native_vision"), {})
    def _build_current_time_message(self) -> dict[str, str] | None:
        """渲染"回复前"追加的 <当前时间> user 块;关闭或为空时返回 None。"""
        builder = self._prompt_builder
        render = getattr(builder, "build_current_time_message", None)
        if callable(render):
            return render()
        if not self._prompt_section_enabled("current_time"):
            return None
        text = render_template(
            self._prompt_template("current_time"), get_current_time_values()
        )
        if not text:
            return None
        return {"role": "user", "content": text}
    def _build_short_time_message(self) -> dict[str, str] | None:
        """渲染同一轮管线激活内第 2 次起的短时间戳 user 块;关闭或为空时返回 None。"""
        builder = self._prompt_builder
        render = getattr(builder, "build_short_time_message", None)
        if callable(render):
            return render()
        if not self._prompt_section_enabled("current_time_short"):
            return None
        text = render_template(
            self._prompt_template("current_time_short"), get_current_time_values()
        )
        if not text:
            return None
        return {"role": "user", "content": text}
    def _build_avoid_repeat_message(self) -> dict[str, str] | None:
        """渲染防重复提醒 user 块（每次管线激活追加一次）;分区关闭或为空时返回 None。"""
        if not self._prompt_section_enabled("avoid_repeat"):
            return None
        text = self._prompt_template("avoid_repeat")
        if not text:
            return None
        return {"role": "user", "content": text}
    def _at_mention_wait_message(self, event: ReplyEvent) -> dict[str, str] | None:
        """被 @ 触发的那一轮追加的等待指引；其余情况返回 None。

        分工：[at_mention_wait] 与 chat.at_mention_reply_delay_seconds 是同一件事的两半 ——
        本体延迟默认已关（0，被 @ 立即回复），「要不要等对方补充」交给模型自己判断：
        对方没说要我做什么才 wait 五秒。
        走 user 块而不是 system 前缀：它只在本轮出现，混进 system 会让那段稳定前缀
        不再逐字节相同，白白丢掉上下文缓存。
        """
        if not self._prompt_section_enabled("at_mention_wait"):
            return None
        if event.conversation_ref is None or event.conversation_ref.kind != "group":
            return None
        willing = self._willing_service
        message = event.message
        if willing is None or message is None:
            return None
        try:
            mentioned = bool(willing.is_at_mentioned(message))
        except Exception:
            return None
        if not mentioned:
            return None
        text = render_template(self._prompt_template("at_mention_wait"), {})
        if not text:
            return None
        return {"role": "user", "content": text}
    def _nudge_text(self) -> str:
        """沉默提醒文本;[silent_nudge] 分区优先,分区缺失时用内置兜底文本。"""
        text = self._prompt_template("silent_nudge")
        return text or _SILENT_NUDGE_TEXT
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
        enabled, first_rounds, _repeat_rounds, seconds, max_emitted = (
            self._get_silent_nudge_settings()
        )
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
    @staticmethod
    def _render_skills(skills: list[Any]) -> str:
        lines = [
            "当用户请求与以下技能相关的事情时，先调用 skills__read_manifest 读取对应技能说明，"
            "再按说明逐步操作（如需要，可用 skills__read_resource 读取技能目录内的参考资料）。"
        ]
        for skill in skills:
            skill_id = getattr(skill, "qualified_name", None) or skill.name
            description = getattr(skill, "description", "") or ""
            lines.append(
                f'<skill id="{_xml_escape(str(skill_id))}" description="{_xml_escape(str(description))}" />'
            )
        return "\n".join(lines)
    def _render_resume_context(self, new_member_text: str) -> str:
        """渲染群聊挂起恢复的说明文本(模板来自 [group_chat_resume])。"""
        builder = self._prompt_builder
        render = getattr(builder, "build_group_chat_resume_text", None)
        if callable(render):
            return render(new_member_profiles=new_member_text)
        template = self._prompt_template("group_chat_resume")
        values = get_current_time_values()
        values["new_member_profiles"] = new_member_text
        return render_template(template, values)
