"""总结提示词：摘要/群资料上限、待总结消息渲染与完整提示词拼装。"""

from __future__ import annotations

from typing import Any

from neobot_app.time_context import get_current_time_and_lunar_date

from .helpers import _format_sender, _normalize_counter_message


class SummaryPromptMixin:
    """档案自动总结的提示词渲染。"""

    def _summary_limits(self) -> tuple[int, int]:
        """返回 (个人 summary 上限, 群聊 summary 上限)。"""
        archive = getattr(
            getattr(getattr(self._config, "agent", None), "memory", None),
            "archive",
            None,
        )
        user_limit = 500
        group_limit = 1500
        if archive is not None:
            raw_user = getattr(archive, "max_chars", None)
            if isinstance(raw_user, int) and raw_user > 0:
                user_limit = raw_user
            raw_group = getattr(archive, "group_profile_max_chars", None)
            if isinstance(raw_group, int) and raw_group > 0:
                group_limit = raw_group
        return user_limit, group_limit

    def _render_recent_messages(self, messages: list[Any]) -> tuple[str, list[int]]:
        """渲染待总结消息：每条截断到 prompt_snippet_chars，返回 (文本, 被截断的序号)。

        截断的消息可由模型用 archive_crud__read_pending_messages 按需读取全文，
        避免把超长消息全文注入提示词。
        """
        snippet_chars = self._prompt_snippet_chars
        lines: list[str] = []
        truncated: list[int] = []
        for index, message in enumerate(messages, start=1):
            item = _normalize_counter_message(message)
            text = item["text"]
            if snippet_chars > 0 and len(text) > snippet_chars:
                text = f"{text[:snippet_chars]}…"
                truncated.append(index)
            lines.append(f"[{index}] {_format_sender(item)}: {text}")
        return "\n".join(lines), truncated

    # ── 提示词规范化：实现 agent_prompt_parts() 即被分析页自动收集 ──

    agent_name = "档案自动总结 Agent"
    agent_note = "空会话 + 群聊模板；运行时还会按会话追加用户画像/好感度/条目归档等指令"

    def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
        from neobot_app.analysis.prompt_analysis import tools_to_text

        try:
            prompt = self._build_summary_prompt(
                conversation_kind="group", conversation_id="0", messages=[]
            )
        except Exception as exc:
            prompt = f"（装配失败: {type(exc).__name__}: {exc}）"
        parts = [("总结指令（群聊 · 空会话）", "system", prompt)]
        definitions = list(getattr(self, "_tool_definitions", []) or [])
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

    def _build_summary_prompt(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        messages: list[Any],
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        kind_label = (
            f"群聊(群号:{conversation_id})"
            if conversation_kind == "group"
            else f"私聊(QQ号:{conversation_id})"
        )
        conversation_key = self._counter_key(conversation_kind, conversation_id)
        recent, truncated_indices = self._render_recent_messages(messages)

        user_limit, group_limit = self._summary_limits()
        if conversation_kind == "group":
            summary_table = "group_summary"
            full_table = "group_profile"
            summary_limit = group_limit
            content_scope = (
                "the group's stable traits: members, atmosphere, inside jokes, "
                "common topics, group norms, recurring events"
            )
        else:
            summary_table = "user_summary"
            full_table = "user_profile"
            summary_limit = user_limit
            content_scope = (
                "the user's stable traits: preferences, interests, hobbies, personality, "
                "important life events, relationships, recurring concerns"
            )

        profile_instruction = (
            f"\nUpdate the archive records INCREMENTALLY with the available tools. "
            f"Never resend a whole record unless you are explicitly compressing it.\n"
            f"1. '{full_table}' (key='{conversation_id}') — the full long-term archive "
            f"(unabridged, keeps growing).\n"
            f"   - New stable facts: archive_crud__patch_archive with op='append'. "
            f"Send ONLY the new lines; do NOT read the record first and do NOT rewrite it.\n"
            f"   - Existing content that must be corrected or merged: locate it with "
            f"archive_crud__read_archive (mode='outline'), read only the relevant page "
            f"(offset, negative offset reads from the tail), then edit it with "
            f"patch_archive (op='replace'/'delete').\n"
            f"   - save_archive on this table is forbidden unless the record must be "
            f"fully rewritten.\n"
            f"2. '{summary_table}' (key='{conversation_id}') — the strict-length summary.\n"
            f"   Structure: write an OVERALL summary of {content_scope} FIRST at the very top, "
            f"then summarize the recent content item by item (chronological order).\n"
            f"   HARD LIMIT: {summary_limit} characters. This is the ONLY record you may "
            f"rewrite with archive_crud__save_archive, and only when it actually needs to "
            f"change. If it is already at/near the limit, compress it (merge into a tighter "
            f"overall summary + chronological digest); NEVER exceed the limit.\n"
        )
        favorability_instruction = (
            f"\nFor each active speaker in the recent messages, evaluate their behavior "
            f"(attitude, interaction quality, cooperativeness, etc.) and use "
            f"favorability__update_favorability to adjust their favorability. "
            f"Positive behavior increases favorability, negative behavior decreases it. "
            f"Each change must be within ±{self._favorability_max_change}. "
            f"Only adjust for users who clearly showed notable behavior worth recording.\n"
        ) if conversation_kind == "group" else (
            f"\nEvaluate the user's behavior in the recent messages (attitude, interaction "
            f"quality, cooperativeness, etc.) and use favorability__update_favorability "
            f"(user_id='{conversation_id}') to adjust their favorability. "
            f"Positive behavior increases favorability, negative behavior decreases it. "
            f"Change must be within ±{self._favorability_max_change}. "
            f"Only adjust if the user clearly showed notable behavior worth recording.\n"
        )

        item_instruction = ""
        if self._item_archive_enabled:
            item_instruction = (
                f"\n3. '{self._item_archive_table}' — items, events, or topics worth keeping. "
                f"Use descriptive keyword keys joined with underscores (e.g. 'game_原神' or "
                f"'event_2026春游'). For a new item call archive_crud__patch_archive "
                f"(op='append') with a compact note — no read needed. Only if the item "
                f"already exists, read it first and then patch or merge it.\n"
            )
        truncation_note = ""
        if truncated_indices:
            shown = ",".join(str(index) for index in truncated_indices[:20])
            truncation_note = (
                f"\nMessage texts marked with … were truncated (indices: {shown}"
                f"{'...' if len(truncated_indices) > 20 else ''}). "
                f"If the full text matters, call archive_crud__read_pending_messages with "
                f"conversation_key='{conversation_key}' and indices=[...]; "
                f"only fetch what you actually need.\n"
            )
        overflow_note = ""
        overflow_limit = getattr(self, "_overflow_max_total_chars", 0)
        if overflow_limit > 0:
            overflow_note = (
                f"\nArchive records have a storage cap of {overflow_limit} characters per record. "
                f"Keep appends compact; a record that exceeds the cap is compressed automatically "
                f"in the background, so never rewrite a whole record just to shrink it yourself.\n"
            )
        return (
            f"Current time: {current_time}\n"
            f"Conversation: {kind_label}\n"
            f"conversation_key: {conversation_key}\n"
            f"The messages below were generated shortly before this time. "
            f"Use the available tools to update the archive records based on these messages.\n"
            f"{overflow_note}{profile_instruction}{favorability_instruction}{item_instruction}"
            f"{truncation_note}"
            f"\nRecent messages (each line is '[index] sender: text'):\n{recent}"
        )
