"""队列公共类型：消息别名、条目类型枚举与各类队列条目 dataclass。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
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
    #: 非发送类工具调用（web_search 等）：没有对应聊天消息，但要在重置后的历史里可见
    TOOL_CALL = "tool_call"


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

    #: message_id 仍是后端 int；操作者 ID 可能是官方 openid 字符串
    target_message_id: int
    emoji_id: int
    operator_user_id: int | str
    operator_name: str

@dataclass
class PokeEntry:
    """Poke (戳一戳) event entry。"""

    #: 用户/群 ID 可能是官方 openid 字符串（不做 int() 转换）
    sender_id: int | str
    user_id: int | str
    target_id: int | str
    sub_type: str
    group_id: int | str | None = None
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
class SelfSentToolCall:
    """Bot 自身发言背后的工具调用记录。

    入队时挂在对应消息上，回复管线重置（寿命耗尽 / 挂起恢复）后据此把历史
    重建成 assistant.tool_calls + tool 回执，模型才能看到「自己发过图/语音/
    长回复」以及当时的参数与索引，而不是一段无法归因的文本。
    """

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    #: 工具是否成功（失败/超时也记一条，但显示上不暴露内容）
    ok: bool = True
    #: compact 显示：只回放 name + 成败，不回放参数/结果（非发送工具用）
    compact: bool = False
    #: 模型给的 tool_call id（同一次调用可对齐 assistant.tool_calls 与 tool 回执）
    call_id: str = ""


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
    #: Bot 自身发言对应的工具调用（仅 self-sent 消息有）；随条目一起进/出队列，
    #: 因此「早于最早保留聊天记录」的工具上下文会随聊天记录一起被丢弃。
    tool_call: Optional[SelfSentToolCall] = None
    #: 该条目占用的容量权重（入队时固化）。
    #: 驱逐与「按权重取最近消息」必须读同一个值：此前驱逐按 kind 重算
    #: （MESSAGE 恒为 1.0），而入队按内容计算（合并转发为 forward_weight），
    #: 导致权重账本单调虚高、队列提前丢弃真实消息。
    weight: float = 1.0
