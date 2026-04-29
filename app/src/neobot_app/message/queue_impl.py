"""Enhanced message queue implementation."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
from enum import Enum
import json
import re
from typing import Callable, Deque, Dict, Iterator, List, Optional, Union

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.model.notice import GroupMessageDelete, PrivateMessageDelete
from neobot_adapter.model.response import GetSignalMsgData, GetSignalMsgResponse
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.time_context import epoch_seconds_int, from_epoch_seconds

MessageType = Union[PrivateMessage, GroupMessage, GetSignalMsgResponse, GetSignalMsgData]
QueueMessage = Union[PrivateMessage, GroupMessage]
RecallNotice = Union[PrivateMessageDelete, GroupMessageDelete]
SegmentFormatter = Callable[[Dict[str, object]], str]


class MessageQueueType(Enum):
    """Message queue type."""

    PRIVATE = "private"
    GROUP = "group"


class QueueEntryType(Enum):
    """Queue entry kind."""

    MESSAGE = "message"
    TIMESTAMP = "timestamp"
    RECALL = "recall"
    REACTION = "reaction"
    POKE = "poke"


@dataclass
class QueueStats:
    """Per-queue stats."""

    total_messages: int = 0
    oldest_message_id: Optional[int] = None
    newest_message_id: Optional[int] = None
    dropped_messages: int = 0


@dataclass
class ReactionEntry:
    """Emoji reaction on a message."""

    target_message_id: int
    emoji_id: int
    operator_user_id: int
    operator_name: str


@dataclass
class PokeEntry:
    """Poke (戳一戳) event entry."""

    sender_id: int
    user_id: int
    target_id: int
    sub_type: str
    group_id: int | None = None
    sender_name: str = ""
    target_name: str = ""
    action_text: str = ""


@dataclass
class QueueEntry:
    """Single queue event."""

    kind: QueueEntryType
    occurred_at: Optional[int] = None
    message: Optional[QueueMessage] = None
    notice: Optional[RecallNotice] = None
    recalled_message: Optional[QueueMessage] = None
    reaction: Optional[ReactionEntry] = None
    poke: Optional[PokeEntry] = None
    replied_messages: List[QueueMessage] = field(default_factory=list)


class MessageQueue:
    """Queue with timestamps, recall events, and text/diff rendering."""

    def __init__(
        self,
        max_size: int = 100,
        *,
        timestamp_interval_seconds: int = 300,
        cq_fallback_max_length: int = 100,
        poke_weight: float = 0.2,
        reaction_weight: float = 0.2,
        forward_weight: int = 2,
        bot_account: int | None = None,
        reply_blacklist: set[int] | None = None,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")
        if timestamp_interval_seconds < 0:
            raise ValueError("timestamp_interval_seconds must be greater than or equal to 0")
        if cq_fallback_max_length <= 0:
            raise ValueError("cq_fallback_max_length must be greater than 0")

        self.max_size = max_size
        self.timestamp_interval_seconds = timestamp_interval_seconds
        self.cq_fallback_max_length = cq_fallback_max_length
        self.poke_weight = max(0.0, min(1.0, poke_weight))
        self.reaction_weight = max(0.0, min(1.0, reaction_weight))
        self.forward_weight = max(1, min(10, forward_weight))
        self.bot_account = bot_account
        self._reply_blacklist = reply_blacklist or set()
        self._queues: Dict[str, Deque[QueueEntry]] = {}
        self._stats: Dict[str, QueueStats] = {}
        self._message_counts: Dict[str, int] = {}
        self._weighted_counts: Dict[str, float] = {}
        self._last_message_times: Dict[str, Optional[int]] = {}
        self._last_reply_positions: Dict[str, int] = {}

    def _convert_message(self, message: MessageType) -> QueueMessage:
        if isinstance(message, (PrivateMessage, GroupMessage)):
            return message

        if isinstance(message, GetSignalMsgResponse):
            if not message.data:
                raise ValueError("GetSignalMsgResponse.data is None")
            msg_data = message.data
        elif isinstance(message, GetSignalMsgData):
            msg_data = message
        else:
            raise TypeError(f"Unsupported message type: {type(message)}")

        data_dict = msg_data.model_dump()
        if msg_data.group_id is not None:
            return safe_parse_model(data_dict, GroupMessage)
        return safe_parse_model(data_dict, PrivateMessage)

    def _get_or_create_queue(self, key: str) -> Deque[QueueEntry]:
        if key not in self._queues:
            self._queues[key] = deque()
            self._stats[key] = QueueStats()
            self._message_counts[key] = 0
            self._weighted_counts[key] = 0.0
            self._last_message_times[key] = None
        return self._queues[key]

    def _get_or_create_stats(self, key: str) -> QueueStats:
        if key not in self._stats:
            self._stats[key] = QueueStats()
        return self._stats[key]

    def _get_message_count(self, key: str) -> int:
        return self._message_counts.get(key, 0)

    def _resolve_occurred_at(self, occurred_at: Optional[int], candidate: object) -> int:
        if occurred_at is not None:
            return occurred_at
        value = getattr(candidate, "time", None)
        if isinstance(value, int):
            return value
        return epoch_seconds_int()

    def _append_timestamp_if_needed(
        self,
        key: str,
        occurred_at: int,
        *,
        include_on_empty: bool = True,
    ) -> None:
        queue = self._get_or_create_queue(key)
        last_message_time = self._last_message_times.get(key)
        if self._get_message_count(key) == 0:
            if include_on_empty:
                queue.append(
                    QueueEntry(kind=QueueEntryType.TIMESTAMP, occurred_at=occurred_at)
                )
            return
        if last_message_time is None:
            return
        if occurred_at - last_message_time <= self.timestamp_interval_seconds:
            return
        queue.append(QueueEntry(kind=QueueEntryType.TIMESTAMP, occurred_at=occurred_at))

    def _get_entry_weight(self, kind: QueueEntryType) -> float:
        """Return the weight for a given entry kind."""
        if kind == QueueEntryType.POKE:
            return self.poke_weight
        if kind == QueueEntryType.REACTION:
            return self.reaction_weight
        return 1.0

    def _compute_message_weight(self, message: QueueMessage) -> float:
        """Compute capacity weight for a message; forward messages consume more."""
        if message.message:
            for segment in message.message:
                seg_type = getattr(segment, "type", None)
                if isinstance(seg_type, Enum):
                    seg_type = seg_type.value
                if str(seg_type) == "forward":
                    return float(self.forward_weight)
        if message.raw_message and "[CQ:forward" in str(message.raw_message):
            return float(self.forward_weight)
        return 1.0

    def _ensure_capacity_for_non_timestamp_entry(self, key: str, entry_weight: float = 1.0) -> None:
        queue = self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        weighted_count = self._weighted_counts.get(key, 0.0)
        if weighted_count + entry_weight <= self.max_size:
            return

        while queue:
            dropped_entry = queue.popleft()
            if dropped_entry.kind == QueueEntryType.TIMESTAMP:
                continue

            self._message_counts[key] -= 1
            self._weighted_counts[key] -= self._get_entry_weight(dropped_entry.kind)
            stats.dropped_messages += 1
            break

        self._refresh_oldest_message_id(key)

    def _refresh_oldest_message_id(self, key: str) -> None:
        stats = self._get_or_create_stats(key)
        stats.oldest_message_id = None
        for entry in self._queues.get(key, ()):
            if entry.kind == QueueEntryType.MESSAGE and entry.message and entry.message.message_id is not None:
                stats.oldest_message_id = entry.message.message_id
                return

    def _push_message(
        self,
        key: str,
        message: MessageType,
        *,
        occurred_at: Optional[int] = None,
        include_initial_timestamp: bool = True,
        replied_messages: Optional[List[MessageType]] = None,
    ) -> None:
        converted_message = self._convert_message(message)
        converted_replies = [
            self._convert_message(replied_message)
            for replied_message in (replied_messages or [])
        ]
        resolved_time = self._resolve_occurred_at(occurred_at, converted_message)

        self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        self._append_timestamp_if_needed(
            key,
            resolved_time,
            include_on_empty=include_initial_timestamp,
        )
        entry_weight = self._compute_message_weight(converted_message)
        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight)

        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.MESSAGE,
                occurred_at=resolved_time,
                message=converted_message,
                replied_messages=converted_replies,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight
        self._last_message_times[key] = resolved_time

        stats.total_messages += 1
        stats.newest_message_id = converted_message.message_id
        if stats.oldest_message_id is None:
            stats.oldest_message_id = converted_message.message_id

    def push(
        self,
        key: str,
        message: MessageType,
        *,
        occurred_at: Optional[int] = None,
        replied_messages: Optional[List[MessageType]] = None,
    ) -> None:
        self._push_message(
            key,
            message,
            occurred_at=occurred_at,
            replied_messages=replied_messages,
        )

    def push_history(
        self,
        key: str,
        message: MessageType,
        *,
        occurred_at: Optional[int] = None,
    ) -> None:
        self._push_message(
            key,
            message,
            occurred_at=occurred_at,
            include_initial_timestamp=False,
        )

    def push_notice(self, key: str, notice: RecallNotice, *, occurred_at: Optional[int] = None) -> None:
        if not isinstance(notice, (PrivateMessageDelete, GroupMessageDelete)):
            raise TypeError(f"Unsupported notice type: {type(notice)}")

        resolved_time = self._resolve_occurred_at(occurred_at, notice)
        recalled_message: Optional[QueueMessage] = None
        if notice.message_id is not None:
            found = self.find_by_message_id(key, notice.message_id)
            if found is not None:
                recalled_message = copy.deepcopy(found)

        self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=1.0)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.RECALL,
                occurred_at=resolved_time,
                notice=copy.deepcopy(notice),
                recalled_message=recalled_message,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += 1.0
        stats.total_messages += 1
        self._refresh_oldest_message_id(key)

    def push_reaction(self, key: str, reaction: ReactionEntry) -> None:
        """Push an emoji reaction entry.

        Only adds the reaction if the target message still exists in the queue.
        """
        target = self.find_by_message_id(key, reaction.target_message_id)
        if target is None:
            return

        self._get_or_create_queue(key)
        entry_weight = self.reaction_weight
        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.REACTION,
                occurred_at=reaction.target_message_id,
                reaction=reaction,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight

    def push_poke(self, key: str, poke: PokeEntry, *, occurred_at: Optional[int] = None) -> None:
        """Push a poke (戳一戳) event entry."""
        resolved_time = self._resolve_occurred_at(occurred_at, poke)

        self._get_or_create_queue(key)
        entry_weight = self.poke_weight
        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.POKE,
                occurred_at=resolved_time,
                poke=poke,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight

    def _message_entries(self, key: str) -> List[QueueEntry]:
        return [
            entry
            for entry in self._queues.get(key, ())
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]

    def get(self, key: str, index: int = -1) -> Optional[QueueMessage]:
        entries = self._message_entries(key)
        if not entries:
            return None
        try:
            return entries[index].message
        except IndexError:
            return None

    def find_by_message_id(self, key: str, message_id: int) -> Optional[QueueMessage]:
        for entry in reversed(self._queues.get(key, ())):
            if entry.kind != QueueEntryType.MESSAGE or entry.message is None:
                continue
            if entry.message.message_id == message_id:
                return entry.message
        return None

    def find_by_position(self, key: str, position: int) -> Optional[QueueMessage]:
        return self.get(key, position)

    def size(self, key: Optional[str] = None) -> int:
        if key is None:
            return sum(self._message_counts.values())
        return self._get_message_count(key)

    def get_all_keys(self) -> List[str]:
        return list(self._queues.keys())

    def clear(self, key: Optional[str] = None) -> None:
        if key is None:
            self._queues.clear()
            self._stats.clear()
            self._message_counts.clear()
            self._weighted_counts.clear()
            self._last_message_times.clear()
            return

        self._queues.pop(key, None)
        self._stats.pop(key, None)
        self._message_counts.pop(key, None)
        self._weighted_counts.pop(key, None)
        self._last_message_times.pop(key, None)

    def iterate_from_oldest(self, key: str) -> Iterator[QueueMessage]:
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")
        for entry in self._queues[key]:
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                yield entry.message

    def iterate_from_newest(self, key: str) -> Iterator[QueueMessage]:
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")
        for entry in reversed(self._queues[key]):
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                yield entry.message

    def get_stats(self, key: str) -> Optional[QueueStats]:
        return self._stats.get(key)

    def clone(self, key: Optional[str] = None) -> "MessageQueue":
        cloned = MessageQueue(
            max_size=self.max_size,
            timestamp_interval_seconds=self.timestamp_interval_seconds,
            cq_fallback_max_length=self.cq_fallback_max_length,
            poke_weight=self.poke_weight,
            reaction_weight=self.reaction_weight,
            forward_weight=self.forward_weight,
            bot_account=self.bot_account,
            reply_blacklist=self._reply_blacklist,
        )

        if key is None:
            keys = self._queues.keys()
        else:
            keys = [key] if key in self._queues else []

        for queue_key in keys:
            cloned._queues[queue_key] = deque(copy.deepcopy(list(self._queues[queue_key])))
            cloned._stats[queue_key] = copy.deepcopy(self._stats.get(queue_key, QueueStats()))
            cloned._message_counts[queue_key] = self._message_counts.get(queue_key, 0)
            cloned._weighted_counts[queue_key] = self._weighted_counts.get(queue_key, 0.0)
            cloned._last_message_times[queue_key] = self._last_message_times.get(queue_key)
            if queue_key in self._last_reply_positions:
                cloned._last_reply_positions[queue_key] = self._last_reply_positions[queue_key]

        return cloned

    def get_last_message_id(self, key: str) -> int | None:
        """获取队列中最后一条消息的 message_id，用于记录回复前位置。"""
        queue = self._queues.get(key)
        if queue is None or not queue:
            return None
        for idx in range(len(queue) - 1, -1, -1):
            if queue[idx].kind == QueueEntryType.MESSAGE and queue[idx].message is not None:
                return queue[idx].message.message_id
        return None

    def set_last_reply_position(self, key: str, before_message_id: int | None = None) -> None:
        """记录上次回复位置。若提供 before_message_id，直接使用该值。"""
        if before_message_id is not None:
            self._last_reply_positions[key] = before_message_id
            return
        queue = self._queues.get(key)
        if queue is None or not queue:
            return
        # 从后往前找最后一条 MESSAGE 类型条目，记录其在 deque 中的位置
        for idx in range(len(queue) - 1, -1, -1):
            if queue[idx].kind == QueueEntryType.MESSAGE and queue[idx].message is not None:
                message_id = queue[idx].message.message_id
                if message_id is not None:
                    self._last_reply_positions[key] = message_id
                return

    def get_last_reply_position(self, key: str) -> int | None:
        """获取上次回复的最后一条消息的 message_id。"""
        return self._last_reply_positions.get(key)

    def get_last_reply_info(self, key: str) -> str:
        """生成'上次回复到'信息文本，用于提示词。"""
        last_msg_id = self._last_reply_positions.get(key)
        if last_msg_id is None:
            return ""
        # 查找该 message_id 在队列中的位置索引
        queue = self._queues.get(key)
        if queue is None:
            return ""
        position = None
        for idx, entry in enumerate(queue):
            if (
                entry.kind == QueueEntryType.MESSAGE
                and entry.message is not None
                and entry.message.message_id == last_msg_id
            ):
                position = idx
                break
        if position is not None:
            return f"上次回复之后的新消息（从第 {position + 1} 条开始）"
        return f"上次回复到 message_id={last_msg_id}"

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
        """Check if the latest message is someone @-mentioning the bot and not in reply blacklist."""
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

    def diff_to_text(self, previous: "MessageQueue", key: str) -> str:
        current_entries = list(self._queues.get(key, ()))
        previous_entries = list(previous._queues.get(key, ()))
        if not current_entries:
            return ""
        if not previous_entries:
            text = self._entries_to_text(current_entries)
            if self._should_request_reply(current_entries):
                text += "\n<最新消息为@你的内容，请回复这句话>"
            return text

        current_non_timestamp = [entry for entry in current_entries if entry.kind != QueueEntryType.TIMESTAMP]
        previous_non_timestamp = [entry for entry in previous_entries if entry.kind != QueueEntryType.TIMESTAMP]
        overlap = self._find_suffix_prefix_overlap(previous_non_timestamp, current_non_timestamp)

        start_index = self._find_full_entry_start_index(current_entries, overlap)
        diff_entries = current_entries[start_index:]
        lines: List[str] = self._build_new_duplicate_notes(
            previous_entries=previous_entries,
            new_entries=diff_entries,
            context_entries=current_entries,
        )
        if overlap == 0 and previous_non_timestamp and current_non_timestamp:
            lines.append(f"[群友发送了太多消息,你只看到了最新的{self.size(key)}条消息]")

        diff_text = self._entries_to_text(diff_entries, context_entries=current_entries)
        if diff_text:
            has_at_bot = self._should_request_reply(current_entries)
            if has_at_bot:
                wrapped = self._wrap_at_in_diff_text(diff_text)
                lines.append(wrapped)
            else:
                lines.append(
                    f"<这是新的可能要回答的内容>\n{diff_text}\n</这是新的可能要回答的内容>"
                )
        if self._should_request_reply(current_entries):
            lines.append("<最新消息为@你的内容，请回复这句话>")
        return "\n".join(line for line in lines if line)

    def _wrap_at_in_diff_text(self, diff_text: str) -> str:
        """In diff text, attempt to wrap the @-bot sentence specifically.

        Falls back to wrapping the entire diff if no @-bot sentence found.
        """
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
        sender_labels = self._build_sender_labels(context_entries or entries)
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
        wrap_at_mention: bool = False,
    ) -> str:
        if entry.kind == QueueEntryType.TIMESTAMP:
            return self._format_timestamp(entry.occurred_at)
        if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
            return self._message_to_text(
                entry.message,
                sender_labels=sender_labels,
                replied_messages=entry.replied_messages,
                wrap_at_mention=wrap_at_mention,
            )
        if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
            return self._recall_to_text(
                entry.notice,
                entry.recalled_message,
                sender_labels=sender_labels,
            )
        if entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
            return self._reaction_to_text(entry.reaction)
        if entry.kind == QueueEntryType.POKE and entry.poke is not None:
            return self._poke_to_text(entry.poke)
        return ""

    @staticmethod
    def _format_timestamp(timestamp: Optional[int]) -> str:
        if timestamp is None:
            return "未知时间"
        dt = from_epoch_seconds(timestamp)
        return f"{dt.year}-{dt.month}-{dt.day}-{dt.hour}:{dt.minute:02d}"

    def _message_to_text(
        self,
        message: QueueMessage,
        *,
        sender_labels: Optional[Dict[int, str]] = None,
        replied_messages: Optional[List[QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
        wrap_at_mention: bool = False,
    ) -> str:
        name = self._message_sender_label(message, sender_labels=sender_labels)
        content = self._render_message_content(
            message,
            replied_messages=replied_messages,
            reply_number_resolver=reply_number_resolver,
            wrap_at_mention=wrap_at_mention,
        )
        return f"{name}: {content}" if content else f"{name}: [无消息内容]"

    def _recall_to_text(
        self,
        notice: RecallNotice,
        recalled_message: Optional[QueueMessage],
        *,
        sender_labels: Optional[Dict[int, str]] = None,
    ) -> str:
        if recalled_message is not None:
            return f"消息撤回: {self._message_to_text(recalled_message)}"
        message_id = notice.message_id if notice.message_id is not None else "未知"
        return f"消息撤回: [原消息不可用, message_id={message_id}]"

    @staticmethod
    def _reaction_to_text(reaction: ReactionEntry) -> str:
        from neobot_app.emoji.mapping import lookup_emoji

        emoji_info = lookup_emoji(reaction.emoji_id)
        if emoji_info is not None:
            emoji_name = emoji_info[0]
        else:
            emoji_name = f"表情#{reaction.emoji_id}"
        return (
            f"{reaction.operator_name} 回应了消息[msg_id={reaction.target_message_id}]:{emoji_name}"
        )

    @staticmethod
    def _poke_to_text(poke: PokeEntry, *, poke_index: int = 0) -> str:
        if poke.action_text:
            text = poke.action_text
        else:
            action_desc = _poke_sub_type_text(poke.sub_type)
            sender = poke.sender_name or f"QQ:{poke.user_id}"
            target = poke.target_name or f"QQ:{poke.target_id}"
            text = f"{sender} 对 {target} 使用了{action_desc}"

        if poke_index == 1:
            return f"{text} [这是QQ戳一戳的消息,会让被戳的人手机轻微震动]"
        if poke_index >= 2:
            return f"{text} [戳一戳消息]"
        return text

    @staticmethod
    def _message_sender_name(message: QueueMessage) -> str:
        sender = message.sender
        if sender is not None and sender.nickname:
            return str(sender.nickname)
        if sender is not None and sender.card:
            return str(sender.card)
        if message.user_id is not None:
            return f"QQ:{message.user_id}"
        return "未知用户"

    @staticmethod
    def _message_sender_identity(message: QueueMessage) -> str:
        if message.user_id is not None:
            return f"qq:{message.user_id}"
        return f"name:{MessageQueue._message_sender_name(message)}"

    def _message_sender_label(
        self,
        message: QueueMessage,
        *,
        sender_labels: Optional[Dict[int, str]] = None,
    ) -> str:
        if sender_labels is not None:
            label = sender_labels.get(id(message))
            if label:
                return label
        return self._message_sender_name(message)

    def _build_sender_labels(self, entries: List[QueueEntry]) -> Dict[int, str]:
        messages = [
            entry.message
            for entry in entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        name_to_sender_ids: Dict[str, set[str]] = {}
        for message in messages:
            name = self._message_sender_name(message)
            sender_id = self._message_sender_identity(message)
            name_to_sender_ids.setdefault(name, set()).add(sender_id)

        duplicate_names = {
            name
            for name, sender_ids in name_to_sender_ids.items()
            if len(sender_ids) > 1
        }
        labels: Dict[int, str] = {}
        for message in messages:
            name = self._message_sender_name(message)
            if name in duplicate_names and message.user_id is not None:
                labels[id(message)] = f"{name}({message.user_id})"
            else:
                labels[id(message)] = name
        return labels

    def _build_new_duplicate_notes(
        self,
        *,
        previous_entries: List[QueueEntry],
        new_entries: List[QueueEntry],
        context_entries: List[QueueEntry],
    ) -> List[str]:
        previous_messages = [
            entry.message
            for entry in previous_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        new_messages = [
            entry.message
            for entry in new_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        if not previous_messages or not new_messages:
            return []

        previous_by_name: Dict[str, Dict[str, QueueMessage]] = {}
        new_by_name: Dict[str, Dict[str, QueueMessage]] = {}

        for message in previous_messages:
            name = self._message_sender_name(message)
            previous_by_name.setdefault(name, {})[self._message_sender_identity(message)] = message
        for message in new_messages:
            name = self._message_sender_name(message)
            new_by_name.setdefault(name, {})[self._message_sender_identity(message)] = message

        notes: List[str] = []
        for name in sorted(set(previous_by_name) & set(new_by_name)):
            previous_senders = previous_by_name[name]
            new_senders = new_by_name[name]
            if not set(new_senders) - set(previous_senders):
                continue
            for message in previous_senders.values():
                if message.user_id is None:
                    continue
                notes.append(f'之前的"{name}"是QQ号为{message.user_id}的')
        return notes

    def _render_message_content(
        self,
        message: QueueMessage,
        *,
        replied_messages: Optional[List[QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
        wrap_at_mention: bool = False,
    ) -> str:
        reply_by_id = {
            reply.message_id: reply
            for reply in (replied_messages or [])
            if reply.message_id is not None
        }
        if message.message:
            parts: list[str] = []
            has_at_bot = False
            for segment in message.message:
                seg_text = self._normalize_inline_text(
                    self._segment_to_text(
                        segment,
                        reply_by_id=reply_by_id,
                        reply_number_resolver=reply_number_resolver,
                    )
                )
                if wrap_at_mention and self._is_at_bot_segment(segment):
                    has_at_bot = True
                    parts.append(
                        f"<这是新的可能要回答的内容>{seg_text}</这是新的可能要回答的内容>"
                    )
                else:
                    parts.append(seg_text)
            if has_at_bot:
                return "".join(parts).strip()
            # No @-bot found with wrapping enabled, wrap the whole message
            if wrap_at_mention:
                text = "".join(parts).strip()
                return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>" if text else "[无消息内容]"
            text = "".join(parts).strip()
            return text or "[无消息内容]"

        if message.raw_message:
            text = self._normalize_inline_text(self._parse_raw_message(message.raw_message))
            if wrap_at_mention:
                text = self._wrap_at_in_raw_message(text, message)
            return text or "[无消息内容]"

        return "[无消息内容]"

    def _is_at_bot_segment(self, segment: object) -> bool:
        """Check if a message segment is an @-mention of the bot."""
        if self.bot_account is None:
            return False
        seg_type = getattr(segment, "type", None)
        if isinstance(seg_type, Enum):
            seg_type = seg_type.value
        if str(seg_type) != "at":
            return False
        raw_data = getattr(segment, "data", None)
        data = self._segment_data_to_dict(raw_data)
        qq = str(data.get("qq") or "")
        return qq == str(self.bot_account)

    def _wrap_at_in_raw_message(self, text: str, _message: QueueMessage) -> str:
        """For raw messages, wrap @-bot mention part with tag."""
        if self.bot_account is None:
            return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>"
        pattern = rf"(@QQ:{self.bot_account}|@[^(\n]*\(QQ:{self.bot_account}\))"
        if re.search(pattern, text):
            return re.sub(
                pattern,
                r"<这是新的可能要回答的内容>\1</这是新的可能要回答的内容>",
                text,
            )
        return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>"

    def _segment_to_text(
        self,
        segment: object,
        *,
        reply_by_id: Optional[Dict[int, QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
    ) -> str:
        msg_type = getattr(segment, "type", None)
        if isinstance(msg_type, Enum):
            msg_type = msg_type.value

        raw_data = getattr(segment, "data", None)
        if raw_data is None and isinstance(segment, dict):
            msg_type = msg_type or segment.get("type")
            raw_data = segment.get("data")

        if msg_type is None:
            return "[未知消息]"

        data = self._segment_data_to_dict(raw_data)
        if str(msg_type) == "reply":
            return self._format_reply_segment(
                data,
                reply_by_id or {},
                reply_number_resolver,
            )
        formatter = self._segment_formatters().get(str(msg_type))
        if formatter is not None:
            return formatter(data)

        cq_code = self._segment_to_cq(str(msg_type), data)
        if len(cq_code) > self.cq_fallback_max_length:
            return "未知过长消息"
        return cq_code

    @staticmethod
    def _segment_data_to_dict(raw_data: object) -> Dict[str, object]:
        if raw_data is None:
            return {}
        if isinstance(raw_data, dict):
            return raw_data
        if hasattr(raw_data, "model_dump"):
            return raw_data.model_dump(exclude_none=True)
        return {}

    def _format_reply_segment(
        self,
        data: Dict[str, object],
        reply_by_id: Dict[int, QueueMessage],
        reply_number_resolver: Optional[Callable[[int], int]] = None,
    ) -> str:
        message_id = _safe_int(data.get("id"))
        if message_id is None:
            return "[回复:消息ID=未知]"
        replied_message = reply_by_id.get(message_id)
        if replied_message is None:
            return f"[回复:消息ID={message_id}]"

        number = reply_number_resolver(message_id) if reply_number_resolver is not None else None
        label = f"回复消息{number}" if number is not None else f"回复消息ID={message_id}"
        sender = self._message_sender_name(replied_message)
        content = self._render_message_content(replied_message)
        return f"[{label}: {sender}: {content}]"

    @staticmethod
    def _segment_formatters() -> Dict[str, SegmentFormatter]:
        return {
            "text": lambda d: str(d.get("text") or ""),
            "face": lambda d: f"[表情:{d.get('id', '未知')}]",
            "record": lambda d: f"[语音:{d.get('file') or d.get('url') or '未知'}]",
            "video": lambda d: f"[视频:{d.get('file') or d.get('url') or '未知'}]",
            "at": lambda d: MessageQueue._format_at_segment(d),
            "image": lambda d: f"[图片:{d.get('file') or d.get('url') or '未知'}]",
            "share": lambda d: f"[分享:{d.get('title') or d.get('url') or '未知链接'}]",
            "reply": lambda d: f"[回复:消息ID={d.get('id', '未知')}]",
            "redbag": lambda d: f"[红包:{d.get('title') or '恭喜发财'}]",
            "poke": lambda d: f"[{_poke_sub_type_text(str(d.get('type', 'poke')))}:QQ={d.get('qq', '未知')}]",
            "gift": lambda d: f"[礼物:QQ={d.get('qq', '未知')},ID={d.get('id', '未知')}]",
            "forward": lambda d: (
                f"[合并转发:ID={d.get('id', '未知')}"
                f"（使用 read_forward_msg 工具查看内容）]"
            ),
            "node": lambda d: f"[转发节点:ID={d.get('id', '未知')},发送者={d.get('name', '未知')}]",
            "xml": lambda d: f"[XML:{d.get('data') or 'XML内容'}]",
            "json": lambda d: f"[JSON:{d.get('data') or 'JSON内容'}]",
            "cardimage": lambda d: f"[卡片图片:{d.get('file') or '未知'}]",
            "tts": lambda d: f"[TTS:{d.get('text') or '语音内容'}]",
            "rps": lambda _d: "[猜拳]",
            "dice": lambda _d: "[骰子]",
            "shake": lambda _d: "[窗口抖动]",
            "anonymous": lambda _d: "[匿名消息]",
            "contact": lambda d: f"[推荐联系人:ID={d.get('id', '未知')}]",
            "location": lambda d: f"[位置:{d.get('title') or '未知位置'}]",
            "music": lambda d: f"[音乐:{d.get('title') or d.get('type') or '未知音乐'}]",
        }

    @staticmethod
    def _format_at_segment(data: Dict[str, object]) -> str:
        qq = data.get("qq", "未知")
        if qq == "all":
            return "@全体成员"
        name = data.get("name")
        if name:
            return f"@{name}(QQ:{qq})"
        return f"@QQ:{qq}"

    @staticmethod
    def _normalize_inline_text(text: str) -> str:
        return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    def _parse_raw_message(self, raw_message: str) -> str:
        pattern = r"\[CQ:([^,\]]+)(?:,([^\]]*))?\]"
        result: List[str] = []
        pos = 0

        for match in re.finditer(pattern, raw_message):
            if match.start() > pos:
                result.append(raw_message[pos:match.start()])

            msg_type = match.group(1)
            params = self._parse_cq_params(match.group(2) or "")
            formatter = self._segment_formatters().get(msg_type)
            cq_code = match.group(0)
            if formatter is not None:
                result.append(formatter(params))
            elif len(cq_code) > self.cq_fallback_max_length:
                result.append("未知过长消息")
            else:
                result.append(cq_code)

            pos = match.end()

        if pos < len(raw_message):
            result.append(raw_message[pos:])

        return "".join(result)

    @staticmethod
    def _parse_cq_params(params_str: str) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if not params_str:
            return params
        for item in params_str.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            params[key] = value
        return params

    @staticmethod
    def _segment_to_cq(msg_type: str, data: Dict[str, object]) -> str:
        if not data:
            return f"[CQ:{msg_type}]"
        parts = []
        for key, value in data.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        params = ",".join(parts)
        return f"[CQ:{msg_type},{params}]" if params else f"[CQ:{msg_type}]"

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, key: str) -> bool:
        return key in self._queues

    def __getitem__(self, key: str) -> Deque[QueueMessage]:
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")
        return deque(
            (
                entry.message
                for entry in self._queues[key]
                if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
            ),
            maxlen=self.max_size,
        )

    def __repr__(self) -> str:
        return (
            "MessageQueue("
            f"max_size={self.max_size}, "
            f"timestamp_interval_seconds={self.timestamp_interval_seconds}, "
            f"forward_weight={self.forward_weight}, "
            f"queues={len(self._queues)})"
        )


def create_message_queue(
    max_size: int = 1000,
    *,
    timestamp_interval_seconds: int = 300,
    cq_fallback_max_length: int = 100,
    poke_weight: float = 0.2,
    reaction_weight: float = 0.2,
    forward_weight: int = 2,
) -> MessageQueue:
    return MessageQueue(
        max_size=max_size,
        timestamp_interval_seconds=timestamp_interval_seconds,
        cq_fallback_max_length=cq_fallback_max_length,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
    )


def _safe_int(value: object) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _poke_sub_type_text(sub_type: str) -> str:
    """将 poke 子类型代码转为中文描述，未知时返回'戳一戳'。"""
    mapping = {
        "poke": "戳一戳",
        "show": "比心",
        "heartbeat": "心跳",
        "like": "点赞",
        "fangdajing": "放大镜",
        "break_out": "敲一敲",
        "sixsixsix": "666",
        "rose": "玫瑰",
        "heart": "比心",
    }
    return mapping.get(str(sub_type).lower(), "戳一戳")
