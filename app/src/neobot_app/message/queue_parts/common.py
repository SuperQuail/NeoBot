"""队列公共类型：消息别名、条目类型枚举与各类队列条目 dataclass。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_adapter.model.notice import GroupMessageDelete
from neobot_adapter.model.notice import PrivateMessageDelete
from neobot_adapter.model.response import GetSignalMsgData
from neobot_adapter.model.response import GetSignalMsgResponse


MessageType = Union[PrivateMessage, GroupMessage, GetSignalMsgResponse, GetSignalMsgData]

QueueMessage = Union[PrivateMessage, GroupMessage]

RecallNotice = Union[PrivateMessageDelete, GroupMessageDelete]

SegmentFormatter = Callable[[Dict[str, object]], str]

class MessageQueueType(Enum):
    """消息队列类型枚举"""

    PRIVATE = "private"
    GROUP = "group"

class QueueEntryType(Enum):
    """队列条目类型。"""

    MESSAGE = "message"
    TIMESTAMP = "timestamp"
    RECALL = "recall"
    REACTION = "reaction"
    POKE = "poke"
    NOTIFICATION = "notification"

@dataclass
class QueueStats:
    """单队列统计信息。"""

    total_messages: int = 0
    oldest_message_id: Optional[int] = None
    newest_message_id: Optional[int] = None
    dropped_messages: int = 0

@dataclass
class ReactionEntry:
    """消息上的表情回应事件。"""

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
class NotificationEntry:
    """后台通知事件的队列快照（对应通知中枢的一次 publish）。

    入队目的是让 agent 在下一轮 transcript 里看到「刚才发生了什么」
    （余额预警、定时任务完成、绘图完成等），而不是只有被单独叫起来时才知道。
    """

    source: str
    content: str

@dataclass
class QueueEntry:
    """单条队列事件。"""

    kind: QueueEntryType
    occurred_at: Optional[int] = None
    message: Optional[QueueMessage] = None
    notice: Optional[RecallNotice] = None
    recalled_message: Optional[QueueMessage] = None
    reaction: Optional[ReactionEntry] = None
    poke: Optional[PokeEntry] = None
    notification: Optional[NotificationEntry] = None
    replied_messages: List[QueueMessage] = field(default_factory=list)
    #: 该条目占用的容量权重（入队时固化）。
    #: 驱逐与「按权重取最近消息」必须读同一个值：此前驱逐按 kind 重算
    #: （MESSAGE 恒为 1.0），而入队按内容计算（合并转发为 forward_weight），
    #: 导致权重账本单调虚高、队列提前丢弃真实消息。
    weight: float = 1.0
