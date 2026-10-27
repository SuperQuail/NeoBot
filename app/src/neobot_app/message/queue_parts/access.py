"""读取路径：按条/按位置取消息、迭代、统计与 dunder 协议。"""

from __future__ import annotations

from collections import deque
from typing import Deque
from typing import Iterator
from typing import List
from typing import Optional

from .common import QueueEntry, QueueEntryType, QueueMessage, QueueStats


class _QueueAccessMixin:
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

    def entries(self, key: str) -> list[QueueEntry]:
        return list(self._queues.get(key, ()))

    def append_entries(self, key: str, entries: list[QueueEntry]) -> None:
        if not entries:
            return
        if key not in self._queues:
            self._queues[key] = deque()
        self._queues[key].extend(entries)

    def clear(self, key: Optional[str] = None) -> None:
        if key is None:
            self._queues.clear()
            self._stats.clear()
            self._message_counts.clear()
            self._weighted_counts.clear()
            self._last_message_times.clear()
            self._command_consumed.clear()
            return

        self._queues.pop(key, None)
        self._stats.pop(key, None)
        self._message_counts.pop(key, None)
        self._weighted_counts.pop(key, None)
        self._last_message_times.pop(key, None)
        self._command_consumed.pop(key, None)

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

    def iterate_entries_from_newest_weighted(
        self, key: str, max_weight: float,
    ) -> Iterator[QueueEntry]:
        queue = self._queues.get(key)
        if queue is None:
            return
        accumulated = 0.0
        first = True
        for entry in reversed(queue):
            if entry.kind == QueueEntryType.TIMESTAMP:
                continue
            weight = entry.weight

            if not first and accumulated + weight > max_weight:
                return
            first = False
            accumulated += weight
            yield entry

    def get_recent_sender_ids(
        self, key: str, max_weight: float,
    ) -> list[int]:
        seen: set[int] = set()
        result: list[int] = []
        for entry in self.iterate_entries_from_newest_weighted(key, max_weight):
            user_id: int | None = None
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                user_id = entry.message.user_id
            elif entry.kind == QueueEntryType.POKE and entry.poke is not None:
                user_id = entry.poke.user_id
            elif entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
                user_id = entry.reaction.operator_user_id
            if user_id is not None and user_id not in seen:
                seen.add(user_id)
                result.append(user_id)
        return result

    def get_recent_messages(
        self, key: str, max_weight: float,
    ) -> list[QueueMessage]:
        result: list[QueueMessage] = []
        for entry in self.iterate_entries_from_newest_weighted(key, max_weight):
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                result.append(entry.message)
        result.reverse()
        return result

    def get_stats(self, key: str) -> Optional[QueueStats]:
        return self._stats.get(key)

    def get_last_message_id(self, key: str) -> int | None:
        queue = self._queues.get(key)
        if queue is None or not queue:
            return None
        for idx in range(len(queue) - 1, -1, -1):
            if queue[idx].kind == QueueEntryType.MESSAGE and queue[idx].message is not None:
                return queue[idx].message.message_id
        return None

    def set_last_reply_position(self, key: str, before_message_id: int | None = None) -> None:
        if before_message_id is not None:
            self._last_reply_positions[key] = before_message_id
            return
        queue = self._queues.get(key)
        if queue is None or not queue:
            return
        for idx in range(len(queue) - 1, -1, -1):
            if queue[idx].kind == QueueEntryType.MESSAGE and queue[idx].message is not None:
                message_id = queue[idx].message.message_id
                if message_id is not None:
                    self._last_reply_positions[key] = message_id
                return

    def get_last_reply_position(self, key: str) -> int | None:
        return self._last_reply_positions.get(key)

    def get_last_reply_info(self, key: str) -> str:
        last_msg_id = self._last_reply_positions.get(key)
        if last_msg_id is None:
            return ""
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
