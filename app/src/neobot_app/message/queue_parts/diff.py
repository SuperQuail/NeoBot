"""差异渲染：上次回复位置之后的新消息与指纹比对。"""

from __future__ import annotations

import json
import re
from typing import Dict
from typing import List
from typing import Optional

from .common import QueueEntry, QueueEntryType, QueueMessage, RecallNotice


class _QueueDiffMixin:
    def to_text(self, key: str, last_reply_message_id: int | None = None, *, all_new: bool = False) -> str:
        if key not in self._queues:
            return ""
        entries = list(self._queues[key])
        separator_index = self._find_separator_index(entries, last_reply_message_id)
        all_new_message = "<当前均为新消息，没有上次回复过的内容>" if all_new else None
        if last_reply_message_id is not None and separator_index is None:
            all_new_message = "<当前均为新消息，没有上次回复过的内容>"
        text = self._entries_to_text(
            entries,
            context_entries=entries,
            separator_after_index=separator_index,
            all_new_message=all_new_message,
        )
        if self._should_request_reply(entries):
            text += "\n<最新消息为@你的内容，请回复这句话>"
        return text

    @staticmethod
    def _find_separator_index(entries: list[QueueEntry], last_reply_message_id: int | None) -> int | None:
        if last_reply_message_id is None:
            return None
        for idx, entry in enumerate(entries):
            if (
                entry.kind == QueueEntryType.MESSAGE
                and entry.message is not None
                and entry.message.message_id == last_reply_message_id
            ):
                return idx
        return None

    def _should_request_reply(self, entries: list[QueueEntry]) -> bool:
        if self.bot_account is None:
            return False
        for entry in reversed(entries):
            if entry.kind != QueueEntryType.MESSAGE or entry.message is None:
                continue
            message = entry.message
            sender_id = getattr(message, "user_id", None)
            if sender_id is not None and sender_id in self._reply_blacklist:
                return False
            if message.message:
                for segment in message.message:
                    segment_type = getattr(segment, "type", None) or ""
                    if str(segment_type) != "at":
                        continue
                    data = getattr(segment, "data", None) or {}
                    qq = str(data.get("qq") or "")
                    if qq == str(self.bot_account):
                        return True
            raw = str(getattr(message, "raw_message", "") or "")
            if f"[CQ:at,qq={self.bot_account}" in raw:
                return True
            return False
        return False

    def _wrap_at_in_diff_text(self, diff_text: str) -> str:
        if self.bot_account is None:
            return f"<这是新的可能要回答的内容>\n{diff_text}\n</这是新的可能要回答的内容>"
        pattern = rf"(@QQ:{self.bot_account}|@[^(\n]*\(QQ:{self.bot_account}\))"
        if re.search(pattern, diff_text):
            lines = diff_text.split("\n")
            wrapped_lines: list[str] = []
            for line in lines:
                if re.search(pattern, line):
                    wrapped_lines.append(
                        re.sub(
                            pattern,
                            r"<这是新的可能要回答的内容>\1</这是新的可能要回答的内容>",
                            line,
                        )
                    )
                else:
                    wrapped_lines.append(line)
            return "\n".join(wrapped_lines)
        return f"<这是新的可能要回答的内容>\n{diff_text}\n</这是新的可能要回答的内容>"

    def _find_suffix_prefix_overlap(
        self,
        previous_entries: List[QueueEntry],
        current_entries: List[QueueEntry],
    ) -> int:
        max_overlap = min(len(previous_entries), len(current_entries))
        current_fingerprints = [self._entry_fingerprint(entry) for entry in current_entries]
        previous_fingerprints = [self._entry_fingerprint(entry) for entry in previous_entries]

        for overlap in range(max_overlap, 0, -1):
            if previous_fingerprints[-overlap:] == current_fingerprints[:overlap]:
                return overlap
        return 0

    def _find_full_entry_start_index(self, entries: List[QueueEntry], non_timestamp_offset: int) -> int:
        if non_timestamp_offset <= 0:
            return 0

        seen = 0
        for index, entry in enumerate(entries):
            if entry.kind == QueueEntryType.TIMESTAMP:
                continue
            seen += 1
            if seen == non_timestamp_offset:
                next_index = index + 1
                while next_index < len(entries) and entries[next_index].kind == QueueEntryType.TIMESTAMP:
                    next_index += 1
                if next_index >= len(entries):
                    return len(entries)
                start_index = next_index
                while start_index > 0 and entries[start_index - 1].kind == QueueEntryType.TIMESTAMP:
                    start_index -= 1
                return start_index
        return len(entries)

    def _entry_fingerprint(self, entry: QueueEntry) -> str:
        if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
            return self._message_fingerprint(entry.message)
        if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
            return self._recall_fingerprint(entry.notice, entry.occurred_at)
        if entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
            return f"reaction:{entry.reaction.target_message_id}:{entry.reaction.emoji_id}:{entry.reaction.operator_user_id}"
        if entry.kind == QueueEntryType.POKE and entry.poke is not None:
            return f"poke:{entry.poke.sender_id}:{entry.poke.target_id}:{entry.poke.sub_type}:{entry.occurred_at or 0}"
        if entry.kind == QueueEntryType.NOTIFICATION and entry.notification is not None:
            return (
                f"notification:{entry.notification.source}:"
                f"{entry.notification.content}:{entry.occurred_at or 0}"
            )
        return f"{entry.kind.value}:{entry.occurred_at or 0}"

    @staticmethod
    def _message_fingerprint(message: QueueMessage) -> str:
        if message.message_id is not None:
            return f"message:{message.message_id}"
        payload = json.dumps(message.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
        return f"message:{payload}"

    @staticmethod
    def _recall_fingerprint(notice: RecallNotice, occurred_at: Optional[int]) -> str:
        parts = [
            type(notice).__name__,
            str(notice.message_id or ""),
            str(getattr(notice, "user_id", "") or ""),
            str(getattr(notice, "operator_id", "") or ""),
            str(occurred_at or 0),
        ]
        return "recall:" + ":".join(parts)

    def _entries_to_text(
        self,
        entries: List[QueueEntry],
        *,
        context_entries: Optional[List[QueueEntry]] = None,
        separator_after_index: int | None = None,
        all_new_message: str | None = None,
    ) -> str:
        sender_labels, sender_labels_by_user = self._build_sender_labels(context_entries or entries)
        lines: list[str] = []
        all_are_new = separator_after_index is None and all_new_message is not None
        if all_new_message is not None:
            lines.append(all_new_message)
        if all_are_new and entries:
            lines.append("<这是新的可能要回答的内容>")
        new_section_opened = False
        poke_count = 0
        for i, entry in enumerate(entries):
            if separator_after_index is not None and i == separator_after_index:
                lines.append("<以上是上次对话回复过的内容>")
                new_section_opened = True
                continue
            if new_section_opened and i == separator_after_index + 1:
                lines.append("<这是新的可能要回答的内容>")
            if entry.kind == QueueEntryType.POKE and entry.poke is not None:
                poke_count += 1
                line = self._poke_to_text(entry.poke, poke_index=poke_count)
            else:
                line = self._entry_to_text(
                    entry, sender_labels=sender_labels,
                    wrap_at_mention=False,
                )
            if line:
                lines.append(line)
        if new_section_opened or (all_are_new and entries):
            lines.append("</这是新的可能要回答的内容>")
        return "\n".join(lines)

    def _entry_to_text(
        self,
        entry: QueueEntry,
        *,
        sender_labels: Optional[Dict[int, str]] = None,
        sender_labels_by_user: Optional[Dict[str, str]] = None,
        wrap_at_mention: bool = False,
    ) -> str:
        if entry.kind == QueueEntryType.TIMESTAMP:
            return self._format_timestamp(entry.occurred_at)
        if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
            return self._message_to_text(
                entry.message,
                sender_labels=sender_labels,
                sender_labels_by_user=sender_labels_by_user,
                replied_messages=entry.replied_messages,
                wrap_at_mention=wrap_at_mention,
            )
        if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
            return self._recall_to_text(
                entry.notice,
                entry.recalled_message,
                sender_labels=sender_labels,
                sender_labels_by_user=sender_labels_by_user,
            )
        if entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
            return self._reaction_to_text(entry.reaction)
        if entry.kind == QueueEntryType.POKE and entry.poke is not None:
            return self._poke_to_text(entry.poke)
        if entry.kind == QueueEntryType.NOTIFICATION and entry.notification is not None:
            return self._notification_to_text(entry.notification)
        return ""
