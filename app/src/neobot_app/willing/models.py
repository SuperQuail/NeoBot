from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from neobot_adapter.model.message import GroupMessage, PrivateMessage

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

ChatMessage = PrivateMessage | GroupMessage


@dataclass(frozen=True, slots=True)
class WillingContext:
    manager_name: str
    conversation_type: str
    conversation_id: str
    sender_id: str
    message_id: int | None
    text: str
    raw_message: str
    queue: "MessageQueue"
    queue_size: int
    queue_text: str
    observe_window: int
    observed_messages_text: tuple[str, ...]
    base_probability: float
    conversation_coefficient: float
    reply_threshold: float
    bot_account: int
    bot_name: str
    bot_aliases: tuple[str, ...]
    mentioned_bot: bool
    called_bot_name: bool
    replied_to_message: bool
    has_question: bool
    matched_keywords: tuple[str, ...]
    is_direct_message: bool
    is_allowed: bool
    block_reason: str
    message: ChatMessage


@dataclass(frozen=True, slots=True)
class WillingDecision:
    manager_name: str
    probability: float
    should_reply: bool
    reasons: tuple[str, ...] = ()


class BaseWillingManager(ABC):
    name = "WillingManager"

    @abstractmethod
    def evaluate(self, context: WillingContext) -> WillingDecision:
        raise NotImplementedError
