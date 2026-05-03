from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_app.message.queue import MessageQueue
from neobot_app.runtime.event_context import EventContext


@dataclass(slots=True)
class MessageContext:
    event: EventContext
    raw_event: dict[str, Any]
    message: PrivateMessage | GroupMessage
    message_type: Literal["private", "group"]
    queue_key: str
    queue: MessageQueue
    text: str = ""
    replied_messages: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
