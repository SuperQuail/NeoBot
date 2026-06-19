"""ReplyEvent — 一次回复的完整生命周期"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, TYPE_CHECKING

from neobot_contracts.models import ConversationRef
from neobot_app.time_context import now_utc

if TYPE_CHECKING:
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_app.willing.models import WillingDecision


class ReplyState(Enum):
    PENDING = auto()
    BUILDING_PROMPT = auto()
    GENERATING = auto()
    SENDING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


_VALID_TRANSITIONS: dict[ReplyState, set[ReplyState]] = {
    ReplyState.PENDING: {ReplyState.BUILDING_PROMPT, ReplyState.FAILED, ReplyState.CANCELLED},
    ReplyState.BUILDING_PROMPT: {ReplyState.GENERATING, ReplyState.FAILED, ReplyState.CANCELLED},
    ReplyState.GENERATING: {ReplyState.SENDING, ReplyState.FAILED, ReplyState.CANCELLED},
    ReplyState.SENDING: {ReplyState.COMPLETED, ReplyState.GENERATING, ReplyState.FAILED, ReplyState.CANCELLED},
}


@dataclass
class ReplyEvent:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: ReplyState = ReplyState.PENDING
    mode: str = "common"
    message: PrivateMessage | GroupMessage | None = None
    conversation_ref: ConversationRef | None = None
    willing_decision: WillingDecision | None = None
    generated_text: str = ""
    send_response: object | None = None
    message_number_map: dict[int, int] = field(default_factory=dict)
    reply_to_number: int | None = None
    created_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None
    pre_reply_message_id: int | None = None
    error: str | None = None
    background_content: str | None = None
    bilibili_context: Any = None  # B站 CommentContext / PrivateMessageContext

    def transition(self, new_state: ReplyState) -> None:
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise RuntimeError(
                f"非法状态转换: {self.state.name} -> {new_state.name}"
            )
        self.state = new_state
        if new_state in (ReplyState.COMPLETED, ReplyState.FAILED, ReplyState.CANCELLED):
            self.completed_at = now_utc()

    @property
    def is_terminal(self) -> bool:
        return self.state in (ReplyState.COMPLETED, ReplyState.FAILED, ReplyState.CANCELLED)
