"""表情包工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

from neobot_app.reply.output_guard import clean_text
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _MAX_EMOJI_PAGE_SIZE, _tool_def


class _EmojiToolsMixin:
    async def _execute_send_emoji(self, args: dict) -> str:
        handler = self._send_emoji
        if handler is None:
            return "错误：send_emoji 处理器未配置"
        try:
            number = int(args.get("number", -1))
        except (ValueError, TypeError):
            return "错误：number 必须为整数"
        emoji_entry = None
        if self._emoji is not None:
            emoji_entry = self._emoji.get_entry(number)
            if emoji_entry is None:
                total = self._emoji.emoji_count
                return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"
        text = clean_text(
            str(args.get("text") or ""), known_sender_names=self._sender_names()
        )
        # 附带文字可为空；清洗掉草稿后仍可单独发送表情包。
        await handler(number=number, text=text)
        entry_name = emoji_entry.file_name if emoji_entry else f"#{number}"
        return f"已发送表情包 {entry_name}"

    def _execute_list_emojis(self, args: dict) -> str:
        """分页列出自定义表情包（文本形式，编号可直接用于发送工具）。"""
        if self._emoji is None:
            return "错误：表情包服务未配置"
        try:
            offset = max(0, int(args.get("offset") or 0))
        except (ValueError, TypeError):
            return "错误：offset 必须为整数"
        raw_limit = args.get("limit")
        limit: int | None = None
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
            except (ValueError, TypeError):
                return "错误：limit 必须为整数"
            if limit <= 0:
                return "错误：limit 必须为正整数"
            limit = min(limit, _MAX_EMOJI_PAGE_SIZE)
        text = self._emoji.build_list_text(offset=offset, limit=limit)
        if not text:
            return "当前没有可用的自定义表情包"
        return text

    def _execute_search_custom_emoji(self, args: dict) -> str:
        if self._emoji is None:
            return "错误：表情包服务未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        results = self._emoji.search_entries(keyword)
        if not results:
            return f'未找到与"{keyword}"相关的自定义表情包'
        lines = [f'搜索"{keyword}"的结果（按使用次数从少到多排列）：']
        for number, entry in results:
            usage_info = f" [已用{entry.use_count}次]" if entry.use_count > 0 else ""
            lines.append(
                f"  #{number}: {entry.analysis_text}{usage_info} ({entry.file_name})"
            )
        return "\n".join(lines)

    async def _execute_react_emoji(self, args: dict) -> str:
        if self._react_emoji is None:
            return "错误：react_emoji 处理器未配置"
        try:
            message_number = int(args.get("message_number", -1))
        except (ValueError, TypeError):
            return "错误：message_number 必须为整数"
        try:
            emoji_id = int(args.get("emoji_id", -1))
        except (ValueError, TypeError):
            return "错误：emoji_id 必须为整数"
        if message_number <= 0:
            return f"错误：message_number 无效，收到 {message_number}"
        if emoji_id < 0:
            return f"错误：emoji_id 无效，收到 {emoji_id}"
        return await self._react_emoji(message_number=message_number, emoji_id=emoji_id)

    def _execute_search_qq_emoji(self, args: dict) -> str:
        if self._search_emoji is None:
            return "错误：search_qq_emoji 处理器未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        return self._search_emoji(keyword=keyword)

    def _define_emoji_tools(self, tools: list[ToolDefinition]) -> None:
        if self._send_emoji is not None or self._emoji is not None:
            tools.append(
                _tool_def(
                    "send_emoji",
                    "向当前会话发送一个表情包图片（可附带可选文字）。"
                    "仅用于只发送表情包而不发送独立文字回复的场景。"
                    "若需要同时发送文字回复和表情包，请使用 send_reply 工具并通过 images 参数指定表情包编号。"
                    "编号用 list_emojis 或 search_custom_emoji 查看（按使用次数从少到多排列，优先用不常用的）。",
                    {
                        "properties": {
                            "number": {
                                "type": "integer",
                                "description": "表情包编号，用 list_emojis / search_custom_emoji 获取。",
                            },
                            "text": {
                                "type": "string",
                                "description": "可选，随表情包一起发送的文字。只放你要说的那句话本身："
                                "不要带编号/发送者名字/[msg_id=...] 等系统标注，也不要写思考过程"
                                "（发送和写回对话历史前会做输出安全清洗）。",
                            },
                        },
                        "required": ["number"],
                    },
                )
            )
        if self._emoji is not None:
            tools.append(
                _tool_def(
                    "list_emojis",
                    "分页查看自定义表情包库（非QQ表情）。返回的编号可直接用于 send_emoji 的 number "
                    "或 send_reply 的 images。列表按使用次数从少到多排列（使用次数均衡器），"
                    "因此优先选前面的编号。不确定用哪个表情包时先调用本工具；"
                    "已经有关键词时用 search_custom_emoji 更省 token。",
                    {
                        "properties": {
                            "offset": {
                                "type": "integer",
                                "description": "从第几个开始（0 起）。翻页时用上一次结果里的提示值。",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "本次返回条数，默认取配置的表情包每页数量。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
            tools.append(
                _tool_def(
                    "search_custom_emoji",
                    "按关键词搜索自定义表情包（非QQ表情）。在表情包描述和文件名中匹配关键词，"
                    "结果按使用次数从少到多排列。已有关键词时优先用本工具；"
                    "没有明确关键词、想看有哪些表情包时用 list_emojis。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": '搜索关键词，如"狗"、"贴纸"、"猫"等。',
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
        if self._react_emoji is not None:
            tools.append(
                _tool_def(
                    "react_emoji",
                    "对指定消息做出QQ表情回应（emoji like）。调用前如果不确定表情ID，"
                    "可先用 search_qq_emoji 工具搜索表情关键词获取表情ID。",
                    {
                        "properties": {
                            "message_number": {
                                "type": "integer",
                                "description": "要回应的消息编号。",
                            },
                            "emoji_id": {
                                "type": "integer",
                                "description": "QQ表情的数字ID。常用表情如：76(赞)、66(爱心)、46(猪头)、182(笑哭)、128(猪)。",
                            },
                        },
                        "required": ["message_number", "emoji_id"],
                    },
                ),
            )
        if self._search_emoji is not None:
            tools.append(
                _tool_def(
                    "search_qq_emoji",
                    "搜索QQ内置表情。按关键词搜索表情名称，返回匹配的表情ID和名称列表。"
                    "找到合适的表情后，可使用 react_emoji 工具发送表情回应。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词，如「猪」、「赞」、「笑哭」等。",
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
