"""Message numbering for agent-mode message references."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue


class MessageNumbering:
    """Manage number <-> message_id mapping and formatted numbered text."""

    def __init__(self) -> None:
        self._mapping: dict[int, int] = {}
        self._reverse: dict[int, int] = {}
        self._next_number: int = 1

    def apply(self, queue: "MessageQueue", queue_key: str) -> str:
        """Number all messages in one queue and render them as text."""
        lines: list[str] = []
        entries = list(queue._queues.get(queue_key, []))
        sender_labels = queue._build_sender_labels(entries)

        for entry in entries:
            if entry.kind.value == "message" and entry.message is not None:
                msg = entry.message
                msg_id = msg.message_id
                if msg_id is None:
                    continue
                number = self._assign_number(msg_id)
                sender = queue._message_sender_label(msg, sender_labels=sender_labels)
                content = queue._render_message_content(msg)
                lines.append(f"{number}: {sender}: {content}")
            elif entry.kind.value == "timestamp":
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
            elif entry.kind.value == "recall":
                lines.append(queue._entry_to_text(entry, sender_labels=sender_labels))
        return "\n".join(lines)

    def apply_new(
        self,
        messages: list,
        queue: "MessageQueue",
        *,
        context_entries: list | None = None,
        previous_entries: list | None = None,
    ) -> str:
        """Number newly arrived queue entries and render them as text."""
        from neobot_app.message.queue_impl import QueueEntryType

        render_context = context_entries or messages
        sender_labels = queue._build_sender_labels(render_context)
        lines: list[str] = []

        if previous_entries is not None:
            lines.extend(
                queue._build_new_duplicate_notes(
                    previous_entries=previous_entries,
                    new_entries=messages,
                    context_entries=render_context,
                )
            )

        for entry in messages:
            if entry.kind != QueueEntryType.MESSAGE or entry.message is None:
                continue
            msg_id = entry.message.message_id
            if msg_id is None:
                continue
            number = self._assign_number(msg_id)
            sender = queue._message_sender_label(entry.message, sender_labels=sender_labels)
            content = queue._render_message_content(entry.message)
            lines.append(f"{number}: {sender}: {content}")
        return "\n".join(lines)

    def apply_raw_messages(self, messages: list, queue: "MessageQueue") -> str:
        """Number raw message objects and render them as text."""
        from neobot_app.message.queue_impl import QueueEntry, QueueEntryType

        entries = [QueueEntry(kind=QueueEntryType.MESSAGE, message=msg) for msg in messages]
        sender_labels = queue._build_sender_labels(entries)
        lines: list[str] = []
        for msg in messages:
            msg_id = msg.message_id
            if msg_id is None:
                continue
            number = self._assign_number(msg_id)
            sender = queue._message_sender_label(msg, sender_labels=sender_labels)
            content = queue._render_message_content(msg)
            lines.append(f"{number}: {sender}: {content}")
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
            "消息格式说明：每条消息以“编号: 用户名: 消息内容”的格式呈现，"
            "编号可用于 reply_to 参数指定回复目标消息。\n"
            "示例：\n"
            "1: 小明: 今天天气真好\n"
            "2: 小红: 是呀，适合出去玩\n"
            "3: 小明: 有人想去看电影吗"
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
