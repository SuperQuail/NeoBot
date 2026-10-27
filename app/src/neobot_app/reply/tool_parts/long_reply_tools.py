"""Markdown 长回复工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import json

from neobot_app.reply.output_guard import clean_text
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def


class _LongReplyToolsMixin:
    async def _execute_send_long_reply(self, args: dict) -> str:
        if self._markdown_image_converter is None:
            return json.dumps(
                {"ok": False, "error": "Markdown 转图片功能未配置"}, ensure_ascii=False
            )

        raw_markdown = str(args.get("markdown") or "").strip()
        sender_names = self._sender_names()
        markdown = clean_text(raw_markdown, known_sender_names=sender_names)
        pre_rendered = str(args.get("image_path") or "").strip()

        if raw_markdown and not markdown.strip() and not pre_rendered:
            return json.dumps(
                {"ok": False, "error": "markdown 清洗后为空，请只提供正文，不要带系统标注或思考草稿"},
                ensure_ascii=False,
            )
        if not markdown.strip() and not pre_rendered:
            return json.dumps(
                {"ok": False, "error": "markdown 和 image_path 至少需要提供一个"},
                ensure_ascii=False,
            )

        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return json.dumps(
                    {"ok": False, "error": f"reply_to 必须为整数，收到 {reply_to}"},
                    ensure_ascii=False,
                )
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return json.dumps(
                    {"ok": False, "error": "mention 必须为整数列表"}, ensure_ascii=False
                )
        caption = clean_text(
            str(args.get("caption") or "").strip(), known_sender_names=sender_names
        )

        if pre_rendered:
            image_path = pre_rendered
        else:
            try:
                image_path = str(await self._markdown_image_converter.convert(markdown))
            except Exception as exc:
                self._logger.error("Markdown 转图片失败", error_type=type(exc).__name__)
                return json.dumps(
                    {"ok": False, "error": "Markdown 转图片失败"}, ensure_ascii=False
                )

        # 调用 orchestrator 提供的 handler 实际发送图片
        if self._send_long_reply is not None:
            await self._send_long_reply(
                image_path=image_path,
                caption=caption,
                reply_to=reply_to,
                mention=mention,
                markdown=markdown,
            )
            self._ai_check_pending = False
        return json.dumps(
            {
                "ok": True,
                "status": "sent",
                "image_path": image_path,
                "caption": caption or None,
                "message": f"已发送Markdown图片{'(预渲染)' if pre_rendered else ''}，路径：{image_path}",
            },
            ensure_ascii=False,
        )

    def _define_long_reply_tool(self, tools: list[ToolDefinition]) -> None:
        if self._markdown_image_converter is not None:
            tools.append(
                _tool_def(
                    "send_long_reply",
                    "发送 Markdown 格式的长回复。这是唯一允许使用 Markdown 格式的发送方式。"
                    "提供 markdown 内容时，系统自动将其转为图片发送。"
                    "如果已有预渲染的图片文件，可提供 image_path 直接发送，"
                    "此时 markdown 仅用于日志记录（仍建议提供以便追溯）。"
                    "适用于包含代码块、表格、数学公式等复杂格式的长文本回复。"
                    r"短公式也可使用；行内公式用 $...$ 或 \(...\)，独立公式用 $$...$$ 或 \[...\]。"
                    "也用于发送解题结果、跨聊天通信结果等需要格式化的内容。"
                    "注意：普通聊天回复请使用 send_reply 发送纯文本（不使用 Markdown）。"
                    "markdown/caption 会先做输出安全清洗，再用于渲染、发送和对话历史；仍必须只放正文本身："
                    "不要带消息编号、发送者名字、[msg_id=...] 这类系统标注，也不要把思考过程或草稿写进去。"
                    "调用后本轮回复视为完成。",
                    {
                        "properties": {
                            "markdown": {
                                "type": "string",
                                "description": r"Markdown 格式的回复内容（image_path 为空时必填）。支持标题、列表、代码块、表格及 KaTeX 数学公式；短公式也可发送。JSON 中反斜杠需正确转义。",
                            },
                            "image_path": {
                                "type": "string",
                                "description": "可选，预渲染的图片文件路径。提供后直接发送该图片，不再重新渲染。解题任务完成通知中会包含此路径。",
                            },
                            "reply_to": {
                                "type": "integer",
                                "description": "可选，要引用回复的消息编号。",
                            },
                            "mention": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效。正文里需要表达 @ 时，没有特殊情况应在 @ 后留一个空格；特殊需要可自行不加。",
                            },
                            "caption": {
                                "type": "string",
                                "description": "可选，随图片一起发送的简短说明文字。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
