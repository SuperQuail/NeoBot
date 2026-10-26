"""工具返回结果的压缩与摘要渲染。"""
from __future__ import annotations

from neobot_app.reply.event import ReplyEvent
from .tool_text import _clip_tool_summary, _render_tool_result_template

class ToolResultsMixin:
    def _get_tool_result_full_keep(self) -> int:
        """重新构建提示词后保留完整内容的最近工具返回条数。"""
        if self._config is None:
            return 10
        value = getattr(self._config.chat, "tool_result_full_keep", 10)
        return value if isinstance(value, int) and value >= 0 else 10
    def _get_tool_result_summary_chars(self) -> int:
        """非基础工具压缩后保留的结果摘要字符数。"""
        if self._config is None:
            return 200
        value = getattr(self._config.chat, "tool_result_summary_chars", 200)
        return value if isinstance(value, int) and value > 0 else 200
    def _render_compressed_tool_result(
        self, tool_name: str, content: object, summary_chars: int
    ) -> str:
        """把一条工具返回渲染成压缩形式。"""
        from neobot_app.reply.tools import BASIC_REPLY_TOOLS

        original = "" if content is None else str(content)
        summary = _clip_tool_summary(original, summary_chars)
        if tool_name in BASIC_REPLY_TOOLS:
            text = _render_tool_result_template(
                self._prompt_template("tool_result_compressed"),
                tool_name=tool_name,
                summary=summary,
                original_chars=len(original),
            )
            return text or f"[已压缩] 工具 {tool_name or '未知工具'} 调用成功。"
        text = _render_tool_result_template(
            self._prompt_template("tool_result_compressed_detail"),
            tool_name=tool_name,
            summary=summary,
            original_chars=len(original),
        )
        return text or summary
    def _compress_stale_tool_results(
        self,
        messages: list[dict],
        compressed_call_ids: set[str],
        tool_names: dict[str, str],
        *,
        event: ReplyEvent | None = None,
        queue_key: str = "",
    ) -> int:
        """压缩较早的工具返回:只保留最近 N 条完整内容,其余压缩。

        在"重新构建/续用提示词"的新一轮开始时调用;已压缩过的条目按
        tool_call_id 去重,不会重复处理。压缩只改写内容,不动消息顺序,
        也不会让 assistant 的 tool_calls 与结果消息失配。
        """
        keep = self._get_tool_result_full_keep()
        indices = [
            index
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if keep >= 0 and len(indices) <= keep:
            return 0
        stale = list(indices) if keep <= 0 else indices[:-keep]
        stale = [
            index
            for index in stale
            if str(messages[index].get("tool_call_id", "")) not in compressed_call_ids
        ]
        if not stale:
            return 0
        summary_chars = self._get_tool_result_summary_chars()
        for index in stale:
            message = messages[index]
            call_id = str(message.get("tool_call_id", ""))
            message["content"] = self._render_compressed_tool_result(
                tool_names.get(call_id, ""), message.get("content"), summary_chars
            )
            if call_id:
                compressed_call_ids.add(call_id)
        if event is not None:
            self._record_debug(
                "tool_results_compressed",
                event,
                queue_key=queue_key,
                compressed_count=len(stale),
                kept_full=len(indices) - len(stale),
            )
        return len(stale)
