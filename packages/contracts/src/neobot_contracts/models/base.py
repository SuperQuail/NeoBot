"""基础模型"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ConversationRef:
    """会话引用，标识一个私聊或群聊"""

    kind: Literal["private", "group"]
    id: str


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """从适配器接收到的消息，与协议无关的统一表示"""

    event_id: str
    conversation: ConversationRef
    sender_id: str
    sender_name: str
    text: str
    occurred_at: datetime
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """记忆条目"""

    conversation: ConversationRef
    speaker_id: str
    content: str
    created_at: datetime
