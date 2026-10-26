"""入队路径：消息转换、权重/容量维护与各类 push 入口。"""

from __future__ import annotations

from collections import deque
import copy
from enum import Enum
from typing import Deque
from typing import List
from typing import Optional
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_adapter.model.notice import GroupMessageDelete
from neobot_adapter.model.notice import PrivateMessageDelete
from neobot_adapter.model.response import GetSignalMsgData
from neobot_adapter.model.response import GetSignalMsgResponse
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.time_context import epoch_seconds_int

from .common import (
    MessageType,
    NotificationEntry,
    PokeEntry,
    QueueEntry,
    QueueEntryType,
    QueueMessage,
    QueueStats,
    ReactionEntry,
    RecallNotice,
)


class _QueuePushMixin:
    # 命令消费标记：事件入口在命令命中后标记消息；挂起管线增量收集时过滤。

    def mark_command_consumed(self, key: str, message_id: Optional[int]) -> None:
        """标记一条消息已被命令系统消费（不再作为新消息触发回复管线）。"""
        if message_id is None:
            return
        bucket = self._command_consumed.get(key)
        if bucket is None:
            bucket = deque(maxlen=self.max_size * 2)
            self._command_consumed[key] = bucket
        if message_id not in bucket:
            bucket.append(message_id)

    def is_command_consumed(self, key: str, message_id: Optional[int]) -> bool:
        """查询消息是否已被命令系统消费。"""
        if message_id is None:
            return False
        bucket = self._command_consumed.get(key)
        return bucket is not None and message_id in bucket

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
                    QueueEntry(
                        kind=QueueEntryType.TIMESTAMP,
                        occurred_at=occurred_at,
                        weight=0.0,
                    )
                )
            return
        if last_message_time is None:
            return
        if occurred_at - last_message_time <= self.timestamp_interval_seconds:
            return
        queue.append(
            QueueEntry(
                kind=QueueEntryType.TIMESTAMP, occurred_at=occurred_at, weight=0.0
            )
        )

    def _compute_message_weight(self, message: QueueMessage) -> float:
        # Bot 自身发言（无论来自实时入队还是后端/本地历史灌入）统一按
        # self_sent_weight 计权：既不挤占用户消息的观测窗口，也不撑大上下文窗口。
        if self.bot_account and message.user_id == self.bot_account:
            return float(self.self_sent_weight)
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

    def _ensure_capacity_for_non_timestamp_entry(self, key: str, entry_weight: float = 1.0) -> bool:
        """按需丢弃最旧的非时间戳条目，直到新条目能放入 max_size 容量内。

        返回 True 表示新条目可以插入；当新条目权重本身超过 max_size（即使空队列
        也放不下）时返回 False，此时调用方应放弃插入并将该条目视为被丢弃。
        """
        queue = self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        weighted_count = self._weighted_counts.get(key, 0.0)
        while queue and weighted_count + entry_weight > self.max_size:
            dropped_entry = queue.popleft()
            if dropped_entry.kind == QueueEntryType.TIMESTAMP:
                continue

            weighted_count -= dropped_entry.weight
            self._message_counts[key] -= 1
            stats.dropped_messages += 1

        self._weighted_counts[key] = weighted_count
        self._refresh_oldest_message_id(key)

        if weighted_count + entry_weight > self.max_size:
            stats.dropped_messages += 1
            return False
        return True

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

        entry_weight = self._compute_message_weight(converted_message)
        if not self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight):
            return

        self._append_timestamp_if_needed(
            key,
            resolved_time,
            include_on_empty=include_initial_timestamp,
        )

        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.MESSAGE,
                occurred_at=resolved_time,
                message=converted_message,
                replied_messages=converted_replies,
                weight=entry_weight,
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
                weight=1.0,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += 1.0
        stats.total_messages += 1
        self._refresh_oldest_message_id(key)

    def push_reaction(self, key: str, reaction: ReactionEntry) -> None:
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
                weight=entry_weight,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight

    def push_poke(self, key: str, poke: PokeEntry, *, occurred_at: Optional[int] = None) -> None:
        resolved_time = self._resolve_occurred_at(occurred_at, poke)

        self._get_or_create_queue(key)
        entry_weight = self.poke_weight
        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.POKE,
                occurred_at=resolved_time,
                poke=poke,
                weight=entry_weight,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight

    def push_notification(
        self, key: str, notification: NotificationEntry, *, occurred_at: Optional[int] = None
    ) -> None:
        """写入一条后台通知条目（低权重；下一轮 transcript 能看到）。

        通知入队只是「让 agent 知道刚才发生了什么」，不承担投递职责——
        投递仍由 BackgroundNotificationHub 完成。因此本方法永不抛异常。
        """
        resolved_time = self._resolve_occurred_at(occurred_at, notification)
        self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        entry_weight = self.self_sent_weight
        self._ensure_capacity_for_non_timestamp_entry(key, entry_weight=entry_weight)
        self._queues[key].append(
            QueueEntry(
                kind=QueueEntryType.NOTIFICATION,
                occurred_at=resolved_time,
                notification=notification,
                weight=entry_weight,
            )
        )
        self._message_counts[key] += 1
        self._weighted_counts[key] += entry_weight
        stats.total_messages += 1
        self._refresh_oldest_message_id(key)
