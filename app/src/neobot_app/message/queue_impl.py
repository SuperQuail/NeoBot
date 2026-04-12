"""Enhanced message queue implementation."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import re
from typing import Callable, Deque, Dict, Iterator, List, Optional, Union

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.model.notice import GroupMessageDelete, PrivateMessageDelete
from neobot_adapter.model.response import GetSignalMsgData, GetSignalMsgResponse
from neobot_adapter.utils.parse import safe_parse_model

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


@dataclass
class QueueStats:
    """Per-queue stats."""

    total_messages: int = 0
    oldest_message_id: Optional[int] = None
    newest_message_id: Optional[int] = None
    dropped_messages: int = 0


@dataclass
class QueueEntry:
    """Single queue event."""

    kind: QueueEntryType
    occurred_at: Optional[int] = None
    message: Optional[QueueMessage] = None
    notice: Optional[RecallNotice] = None
    recalled_message: Optional[QueueMessage] = None


class MessageQueue:
    """Queue with timestamps, recall events, and text/diff rendering."""

    def __init__(
        self,
        max_size: int = 100,
        *,
        timestamp_interval_seconds: int = 300,
        cq_fallback_max_length: int = 100,
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
        self._queues: Dict[str, Deque[QueueEntry]] = {}
        self._stats: Dict[str, QueueStats] = {}
        self._message_counts: Dict[str, int] = {}
        self._last_message_times: Dict[str, Optional[int]] = {}

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
        return int(datetime.now().timestamp())

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

    def _ensure_capacity_for_non_timestamp_entry(self, key: str) -> None:
        queue = self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        if self._get_message_count(key) < self.max_size:
            return

        while queue:
            dropped_entry = queue.popleft()
            if dropped_entry.kind == QueueEntryType.TIMESTAMP:
                continue

            self._message_counts[key] -= 1
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
    ) -> None:
        converted_message = self._convert_message(message)
        resolved_time = self._resolve_occurred_at(occurred_at, converted_message)

        self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        self._append_timestamp_if_needed(
            key,
            resolved_time,
            include_on_empty=include_initial_timestamp,
        )
        self._ensure_capacity_for_non_timestamp_entry(key)

        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.MESSAGE,
                occurred_at=resolved_time,
                message=converted_message,
            )
        )
        self._message_counts[key] += 1
        self._last_message_times[key] = resolved_time

        stats.total_messages += 1
        stats.newest_message_id = converted_message.message_id
        if stats.oldest_message_id is None:
            stats.oldest_message_id = converted_message.message_id

    def push(self, key: str, message: MessageType, *, occurred_at: Optional[int] = None) -> None:
        self._push_message(key, message, occurred_at=occurred_at)

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

        self._ensure_capacity_for_non_timestamp_entry(key)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.RECALL,
                occurred_at=resolved_time,
                notice=copy.deepcopy(notice),
                recalled_message=recalled_message,
            )
        )
        self._message_counts[key] += 1
        stats.total_messages += 1
        self._refresh_oldest_message_id(key)

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
            self._last_message_times.clear()
            return

        self._queues.pop(key, None)
        self._stats.pop(key, None)
        self._message_counts.pop(key, None)
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
        )

        if key is None:
            keys = self._queues.keys()
        else:
            keys = [key] if key in self._queues else []

        for queue_key in keys:
            cloned._queues[queue_key] = deque(copy.deepcopy(list(self._queues[queue_key])))
            cloned._stats[queue_key] = copy.deepcopy(self._stats.get(queue_key, QueueStats()))
            cloned._message_counts[queue_key] = self._message_counts.get(queue_key, 0)
            cloned._last_message_times[queue_key] = self._last_message_times.get(queue_key)

        return cloned

    def to_text(self, key: str) -> str:
        if key not in self._queues:
            return ""
        return self._entries_to_text(list(self._queues[key]))

    def diff_to_text(self, previous: "MessageQueue", key: str) -> str:
        current_entries = list(self._queues.get(key, ()))
        previous_entries = list(previous._queues.get(key, ()))
        if not current_entries:
            return ""
        if not previous_entries:
            return self._entries_to_text(current_entries)

        current_non_timestamp = [entry for entry in current_entries if entry.kind != QueueEntryType.TIMESTAMP]
        previous_non_timestamp = [entry for entry in previous_entries if entry.kind != QueueEntryType.TIMESTAMP]
        overlap = self._find_suffix_prefix_overlap(previous_non_timestamp, current_non_timestamp)

        start_index = self._find_full_entry_start_index(current_entries, overlap)
        diff_entries = current_entries[start_index:]
        lines: List[str] = []
        if overlap == 0 and previous_non_timestamp and current_non_timestamp:
            lines.append(f"[群友发送了太多消息,你只看到了最新的{self.size(key)}条消息]")

        diff_text = self._entries_to_text(diff_entries)
        if diff_text:
            lines.append(diff_text)
        return "\n".join(line for line in lines if line)

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

    def _entries_to_text(self, entries: List[QueueEntry]) -> str:
        lines = [self._entry_to_text(entry) for entry in entries]
        return "\n".join(line for line in lines if line)

    def _entry_to_text(self, entry: QueueEntry) -> str:
        if entry.kind == QueueEntryType.TIMESTAMP:
            return self._format_timestamp(entry.occurred_at)
        if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
            return self._message_to_text(entry.message)
        if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
            return self._recall_to_text(entry.notice, entry.recalled_message)
        return ""

    @staticmethod
    def _format_timestamp(timestamp: Optional[int]) -> str:
        if timestamp is None:
            return "未知时间"
        dt = datetime.fromtimestamp(timestamp)
        return f"{dt.year}-{dt.month}-{dt.day}-{dt.hour}:{dt.minute:02d}"

    def _message_to_text(self, message: QueueMessage) -> str:
        name = self._message_sender_name(message)
        content = self._render_message_content(message)
        return f"{name}: {content}" if content else f"{name}: [无消息内容]"

    def _recall_to_text(
        self,
        notice: RecallNotice,
        recalled_message: Optional[QueueMessage],
    ) -> str:
        if recalled_message is not None:
            return f"消息撤回: {self._message_to_text(recalled_message)}"
        message_id = notice.message_id if notice.message_id is not None else "未知"
        return f"消息撤回: [原消息不可用, message_id={message_id}]"

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

    def _render_message_content(self, message: QueueMessage) -> str:
        if message.message:
            parts = [self._normalize_inline_text(self._segment_to_text(segment)) for segment in message.message]
            text = "".join(parts).strip()
            return text or "[无消息内容]"

        if message.raw_message:
            text = self._normalize_inline_text(self._parse_raw_message(message.raw_message))
            return text or "[无消息内容]"

        return "[无消息内容]"

    def _segment_to_text(self, segment: object) -> str:
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
            "poke": lambda d: f"[戳一戳:QQ={d.get('qq', '未知')}]",
            "gift": lambda d: f"[礼物:QQ={d.get('qq', '未知')},ID={d.get('id', '未知')}]",
            "forward": lambda d: f"[合并转发:ID={d.get('id', '未知')}]",
            "node": lambda d: f"[转发节点:ID={d.get('id', '未知')},名称={d.get('name', '未知')}]",
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
            f"queues={len(self._queues)})"
        )


def create_message_queue(
    max_size: int = 1000,
    *,
    timestamp_interval_seconds: int = 300,
    cq_fallback_max_length: int = 100,
) -> MessageQueue:
    return MessageQueue(
        max_size=max_size,
        timestamp_interval_seconds=timestamp_interval_seconds,
        cq_fallback_max_length=cq_fallback_max_length,
    )
