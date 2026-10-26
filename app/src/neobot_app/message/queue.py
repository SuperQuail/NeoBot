"""消息队列的公开入口：实现按职责拆到 queue_parts/，本模块只保留门面。"""

from __future__ import annotations

from collections import deque
import copy
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional

from .queue_parts.common import (
    MessageType,
    QueueMessage,
    RecallNotice,
    SegmentFormatter,
    MessageQueueType,
    QueueEntryType,
    QueueStats,
    ReactionEntry,
    PokeEntry,
    NotificationEntry,
    QueueEntry,
)
from .queue_parts.helpers import _safe_int as _safe_int, _poke_sub_type_text
from .queue_parts.push import _QueuePushMixin
from .queue_parts.access import _QueueAccessMixin
from .queue_parts.diff import _QueueDiffMixin
from .queue_parts.text import _QueueTextMixin
from .queue_parts.segments import _QueueSegmentMixin

__all__ = [
    "MessageQueue",
    "MessageQueueType",
    "MessageType",
    "NotificationEntry",
    "PokeEntry",
    "QueueEntry",
    "QueueEntryType",
    "QueueMessage",
    "QueueStats",
    "ReactionEntry",
    "RecallNotice",
    "SegmentFormatter",
    "create_message_queue",
]


class MessageQueue(
    _QueuePushMixin,
    _QueueAccessMixin,
    _QueueDiffMixin,
    _QueueTextMixin,
    _QueueSegmentMixin,
):
    """带时间戳、撤回事件及文本/差异渲染的消息队列。"""

    def __init__(
        self,
        max_size: int = 100,
        *,
        timestamp_interval_seconds: int = 300,
        cq_fallback_max_length: int = 100,
        poke_weight: float = 0.2,
        reaction_weight: float = 0.2,
        forward_weight: int = 2,
        self_sent_weight: float = 0.1,
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
        #: Bot 自身发言（含历史灌入与实时入队两个来源）在队列中的容量权重。
        #: 与 poke/reaction 同档：自身发言几乎不挤占用户消息的观测窗口，
        #: 也不撑大上下文窗口；两个来源共用同一权重，避免口径分裂。
        self.self_sent_weight = max(0.0, min(1.0, self_sent_weight))
        self.bot_account = bot_account
        self._reply_blacklist = reply_blacklist or set()
        self._queues: Dict[str, Deque[QueueEntry]] = {}
        self._stats: Dict[str, QueueStats] = {}
        self._message_counts: Dict[str, int] = {}
        self._weighted_counts: Dict[str, float] = {}
        self._last_message_times: Dict[str, Optional[int]] = {}
        self._last_reply_positions: Dict[str, int] = {}
        # 命令系统已消费的消息 message_id（按 queue_key 分桶，有界）。
        # 挂起回复管线收集新消息时必须跳过这些条目，避免 /help 等命令
        # 在命令系统回复后被已运行的 Agent 管线再次拾取并触发回复。
        self._command_consumed: Dict[str, Deque[int]] = {}

    def clone(self, key: Optional[str] = None) -> "MessageQueue":
        cloned = MessageQueue(
            max_size=self.max_size,
            timestamp_interval_seconds=self.timestamp_interval_seconds,
            cq_fallback_max_length=self.cq_fallback_max_length,
            poke_weight=self.poke_weight,
            reaction_weight=self.reaction_weight,
            forward_weight=self.forward_weight,
            self_sent_weight=self.self_sent_weight,
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

    def diff_to_text(self, previous: "MessageQueue", key: str) -> str:
        current_entries = self.entries(key)
        previous_entries = previous.entries(key)
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

    @staticmethod
    def _segment_formatters() -> Dict[str, SegmentFormatter]:
        return {
            "text": lambda d: str(d.get("text") or ""),
            "face": lambda d: f"[表情:{d.get('id', '未知')}]",
            "record": lambda d: f"[语音:{d.get('file') or d.get('url') or '未知'}]",
            "video": lambda d: f"[视频:{d.get('file') or d.get('url') or '未知'}]",
            "at": lambda d: MessageQueue._format_at_segment(d),
            # Keep image references/inline base64 out of the textual prompt.
            # Native image payloads are appended separately with message/index labels.
            "image": lambda d: str(d.get("summary") or "[图片]")[:256],
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
            "cardimage": lambda d: str(d.get("summary") or "[卡片图片]")[:256],
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
    def _message_sender_identity(message: QueueMessage) -> str:
        if message.user_id is not None:
            return f"qq:{message.user_id}"
        return f"name:{MessageQueue._message_sender_name(message)}"

def create_message_queue(
    max_size: int = 1000,
    *,
    timestamp_interval_seconds: int = 300,
    cq_fallback_max_length: int = 100,
    poke_weight: float = 0.2,
    reaction_weight: float = 0.2,
    forward_weight: int = 2,
    self_sent_weight: float = 0.1,
) -> MessageQueue:
    """创建消息队列实例的快捷函数"""
    return MessageQueue(
        max_size=max_size,
        timestamp_interval_seconds=timestamp_interval_seconds,
        cq_fallback_max_length=cq_fallback_max_length,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
        self_sent_weight=self_sent_weight,
    )
