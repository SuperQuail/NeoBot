"""为 agent 模式的消息引用提供消息编号。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue  # noqa: F401  (仅类型标注用)


class MessageNumbering:
    """管理编号与 message_id 的映射，并生成带编号的格式化文本。"""

    def __init__(
        self,
        bot_account: int | None = None,
        *,
        queue: "MessageQueue | None" = None,
        queue_key: str | None = None,
    ) -> None:
        self._mapping: dict[int, int] = {}
        self._reverse: dict[int, int] = {}
        self._next_number: int = 1
        #: Bot 自己的 QQ 号。用于判断某条消息是不是它自己发出的 ——
        #: 自己的发言不渲染「编号: 发送者:」前缀（见 _render_numbered_line）。
        self._bot_account = bot_account
        #: 本会话消息队列（供发送前清洗取「出现过的发送者名字」，见 known_sender_names）。
        self._queue = queue
        self._queue_key = queue_key

    def known_sender_names(self) -> list[str]:
        """本会话出现过的全部发送者显示名（昵称 / 群名片，去重）。

        发送前清洗（reply/output_guard.py）用它认出模型从历史里学来的
        `编号: 名字: ` 前缀。工具层与发送层必须共用同一份集合，否则会出现
        「工具层说已发送、发送层清空丢弃」的静默缝。
        """
        queue = self._queue
        if queue is None:
            return []
        getter = getattr(queue, "sender_labels", None)
        if not callable(getter):
            return []
        try:
            values = getter() if self._queue_key is None else getter(queue_key=self._queue_key)
            return [str(name) for name in (values or []) if str(name or "").strip()]
        except Exception:
            return []

    def _render_numbered_line(
        self,
        message,
        msg_id: int,
        number: int,
        sender: str,
        content: str,
        *,
        replied: bool = False,
    ) -> str:
        """渲染一条带编号的消息行。

        **Bot 自己的发言不带「编号: 发送者:」前缀**（与 prompt/role_messages 的
        assistant 分支同一口径）：历史里出现这种前缀时，模型会把它当成自己该
        输出的格式去模仿（问题报告的根因）。wait 结果、增量注入、文本回退路径
        都必须和聊天记录渲染保持一致，否则同一条管线里一边禁止一边示范。
        """
        is_self = (
            self._bot_account is not None
            and getattr(message, "user_id", None) == self._bot_account
        )
        marker = "[被回复消息] " if replied else ""
        if is_self:
            return f"[msg_id={msg_id}] {marker}{content}"
        return f"[msg_id={msg_id}] {number}: {marker}{sender}: {content}"

    def apply(
        self,
        queue: "MessageQueue",
        queue_key: str,
        last_reply_message_id: int | None = None,
        *,
        all_new: bool = False,
    ) -> str:
        """为一个队列中的所有消息编号并将其渲染为文本。"""
        if self._queue is None:
            self._queue = queue
        self._queue_key = queue_key
        lines: list[str] = []
        entries = queue.entries(queue_key)
        sender_labels, sender_labels_by_user = queue._build_sender_labels(entries)

        found_last_reply = False
        if last_reply_message_id is not None:
            found_last_reply = any(
                entry.kind.value == "message"
                and entry.message is not None
                and entry.message.message_id == last_reply_message_id
                for entry in entries
            )
        if all_new or (last_reply_message_id is not None and not found_last_reply):
            lines.append("<当前均为新消息，没有上次回复过的内容>")

        new_section_opened = False
        new_section_content_emitted = False
        poke_count = 0
        for i, entry in enumerate(entries):
            if new_section_opened and i > 0:
                prev_entry = entries[i - 1]
                if prev_entry.kind.value == "message" and prev_entry.message is not None and prev_entry.message.message_id == last_reply_message_id:
                    lines.append("<这是新的可能要回答的内容>")
                    new_section_content_emitted = True
            if entry.kind.value == "message" and entry.message is not None:
                lines.extend(
                    self._format_replied_messages(
                        entry, queue, sender_labels_by_user=sender_labels_by_user
                    )
                )
                msg = entry.message
                msg_id = msg.message_id
                if msg_id is None:
                    continue
                number = self._assign_number(msg_id)
                sender = queue._message_sender_label(msg, sender_labels=sender_labels, sender_labels_by_user=sender_labels_by_user)
                content = queue._render_message_content(
                    msg,
                    replied_messages=entry.replied_messages,
                    reply_number_resolver=self._assign_number,
                    wrap_at_mention=False,
                )
                lines.append(
                    self._render_numbered_line(msg, msg_id, number, sender, content)
                )
            elif entry.kind.value == "timestamp":
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
            elif entry.kind.value == "recall":
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
            elif entry.kind.value == "reaction" and entry.reaction is not None:
                reaction = entry.reaction
                target_number = self.get_number(reaction.target_message_id)
                if target_number is not None:
                    lines.append(
                        self._format_reaction(reaction, target_number)
                    )
            elif entry.kind.value == "poke" and entry.poke is not None:
                poke_count += 1
                lines.append(queue._poke_to_text(entry.poke, poke_index=poke_count))
            elif entry.kind.value == "notification" and entry.notification is not None:
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
            if last_reply_message_id is not None and entry.kind.value == "message" and entry.message is not None and entry.message.message_id == last_reply_message_id:
                lines.append("<以上是上次对话回复过的内容>")
                new_section_opened = True
                continue
        # 仅在真正输出过新区段开标记时才追加闭合标记(last_reply 在队尾时避免残缺闭合)
        if new_section_opened and new_section_content_emitted:
            lines.append("</这是新的可能要回答的内容>")
        return "\n".join(lines)

    def apply_new(
        self,
        messages: list,
        queue: "MessageQueue",
        *,
        context_entries: list | None = None,
        previous_entries: list | None = None,
    ) -> str:
        """为新到达的队列条目编号并将其渲染为文本。"""
        from neobot_app.message.queue import QueueEntryType

        render_context = context_entries or messages
        sender_labels, sender_labels_by_user = queue._build_sender_labels(render_context)
        lines: list[str] = []

        if previous_entries is not None:
            lines.extend(
                queue._build_new_duplicate_notes(
                    previous_entries=previous_entries,
                    new_entries=messages,
                    context_entries=render_context,
                )
            )

        poke_count = 0
        for entry in messages:
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                lines.extend(
                    self._format_replied_messages(
                        entry, queue, sender_labels_by_user=sender_labels_by_user
                    )
                )
                msg_id = entry.message.message_id
                if msg_id is None:
                    continue
                number = self._assign_number(msg_id)
                sender = queue._message_sender_label(
                    entry.message,
                    sender_labels=sender_labels,
                    sender_labels_by_user=sender_labels_by_user,
                )
                content = queue._render_message_content(
                    entry.message,
                    replied_messages=entry.replied_messages,
                    reply_number_resolver=self._assign_number,
                    wrap_at_mention=False,
                )
                lines.append(
                    self._render_numbered_line(
                        entry.message, msg_id, number, sender, content
                    )
                )
            elif entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
                reaction = entry.reaction
                target_number = self.get_number(reaction.target_message_id)
                if target_number is not None:
                    lines.append(
                        self._format_reaction(reaction, target_number)
                    )
            elif entry.kind == QueueEntryType.RECALL:
                # 撤回事件渲染(与 role_messages 的增量路径一致)
                text = queue._entry_to_text(entry, sender_labels=sender_labels)
                if text:
                    lines.append(text)
            elif entry.kind == QueueEntryType.POKE and entry.poke is not None:
                poke_count += 1
                lines.append(queue._poke_to_text(entry.poke, poke_index=poke_count))
            elif entry.kind == QueueEntryType.NOTIFICATION and entry.notification is not None:
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
        return "\n".join(lines)

    def apply_raw_messages(self, messages: list, queue: "MessageQueue") -> str:
        """为原始消息对象编号并将其渲染为文本。"""
        from neobot_app.message.queue import QueueEntry, QueueEntryType

        entries = [QueueEntry(kind=QueueEntryType.MESSAGE, message=msg) for msg in messages]
        sender_labels, sender_labels_by_user = queue._build_sender_labels(entries)
        lines: list[str] = []
        for msg in messages:
            msg_id = msg.message_id
            if msg_id is None:
                continue
            number = self._assign_number(msg_id)
            sender = queue._message_sender_label(msg, sender_labels=sender_labels, sender_labels_by_user=sender_labels_by_user)
            content = queue._render_message_content(msg)
            lines.append(
                self._render_numbered_line(msg, msg_id, number, sender, content)
            )
        return "\n".join(lines)

    def get_message_id(self, number: int) -> int | None:
        return self._mapping.get(number)

    def get_number(self, message_id: int) -> int | None:
        return self._reverse.get(message_id)

    @property
    def mapping(self) -> dict[int, int]:
        return dict(self._mapping)

    @staticmethod
    def format_example() -> str:
        return (
            "消息格式说明：别人的消息以“[msg_id=真实message_id] 编号: 用户名: 消息内容”的格式呈现。\n"
            "- 行首方括号中的 msg_id= 即真实 OneBot message_id：工具参数需要 message_id 时"
            "（如 message_id、chat: 前缀等），直接使用它，不要再查映射。\n"
            "- 编号（msg_id 之后的数字）用于 reply_to / msg_number 参数指定回复目标消息。\n"
            "例如：[msg_id=1425980020] 1: 小明: 你好\n"
            "- 这套标注只是系统给你阅读用的，**不是你的输出格式**：你自己发言时只发正文，"
            "不要带 [msg_id=...]、编号或发送者名字。\n"
            "- 你自己说过的话在对话里没有编号、也没有 [msg_id=...]，**不要去引用自己的消息**"
            "（reply_to / msg_number 只能指向别人的消息）；要指代自己的话就直接复述那句话。\n"
            "当有人回复消息时，被回复的消息会以“[被回复消息]”前缀单独显示（有自己的编号）：\n"
            "例如：[msg_id=479202588] 1: [被回复消息] 小红: [图片]\n"
            "     [msg_id=1525160030] 6: 唐天: [回复:消息ID=xxx] @bot 解析这张\n"
            "→ 要解析图片，应使用 msg_number=1（被回复消息），非 msg_number=6（回复文字）。"
        )

    def _assign_number(self, message_id: int) -> int:
        existing = self._reverse.get(message_id)
        if existing is not None:
            return existing
        number = self._next_number
        self._mapping[number] = message_id
        self._reverse[message_id] = number
        self._next_number += 1
        return number

    def _format_replied_messages(
        self,
        entry,
        queue: "MessageQueue",
        *,
        sender_labels_by_user: dict | None = None,
    ) -> list[str]:
        lines: list[str] = []
        for replied_message in getattr(entry, "replied_messages", []) or []:
            msg_id = getattr(replied_message, "message_id", None)
            if msg_id is None or self.get_number(msg_id) is not None:
                continue
            number = self._assign_number(msg_id)
            sender = queue._message_sender_label(
                replied_message, sender_labels_by_user=sender_labels_by_user
            )
            content = queue._render_message_content(replied_message)
            lines.append(
                self._render_numbered_line(
                    replied_message, msg_id, number, sender, content, replied=True
                )
            )
        return lines

    @staticmethod
    def _format_reaction(reaction, target_number: int) -> str:
        from neobot_app.emoji.mapping import lookup_emoji

        emoji_info = lookup_emoji(reaction.emoji_id)
        if emoji_info is not None:
            emoji_name = emoji_info[0]
        else:
            emoji_name = f"表情#{reaction.emoji_id}"
        return f"{reaction.operator_name} 回应了消息{target_number}:{emoji_name}"

    @staticmethod
    def _sender_name(message) -> str:
        sender = message.sender
        if sender is not None and sender.nickname:
            return str(sender.nickname)
        if sender is not None and sender.card:
            return str(sender.card)
        if message.user_id is not None:
            return f"QQ:{message.user_id}"
        return "未知用户"

    @staticmethod
    def _render_simple(message) -> str:
        if message.message:
            parts: list[str] = []
            for segment in message.message:
                seg_type = getattr(segment, "type", None)
                if hasattr(seg_type, "value"):
                    seg_type = seg_type.value
                raw_data = getattr(segment, "data", None)
                if isinstance(raw_data, dict):
                    data = raw_data
                elif hasattr(raw_data, "model_dump"):
                    data = raw_data.model_dump(exclude_none=True)
                else:
                    data = {}
                if str(seg_type) == "text":
                    parts.append(str(data.get("text") or ""))
                elif str(seg_type) == "at":
                    qq = data.get("qq", "未知")
                    parts.append(f"@{qq}")
                elif str(seg_type) == "image":
                    parts.append("[图片]")
                elif str(seg_type):
                    parts.append(f"[{seg_type}]")
            return "".join(parts).strip() or "[无消息内容]"
        return str(message.raw_message or "") or "[无消息内容]"
