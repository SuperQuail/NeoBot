"""Conversation-scoped permission for image understanding."""

from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.speaking import SpeechBlocked


def message_conversation(message: Any) -> ConversationRef | None:
    group_id = getattr(message, "group_id", None)
    target = group_id if group_id is not None else getattr(message, "user_id", None)
    if target is None:
        return None
    return ConversationRef("group" if group_id is not None else "private", str(target))


def pipeline_conversation(key: str) -> ConversationRef | None:
    kind, _, target = key.partition(":")
    return ConversationRef(kind, target) if kind in ("group", "private") and target else None


def check_image_policy(adapter: Any, conversation: ConversationRef | None) -> None:
    policy = getattr(getattr(adapter, "core", None), "speaking_policy", None)
    if policy is not None and conversation is not None:
        decision = policy.evaluate(conversation)
        if not decision.allowed:
            raise SpeechBlocked(decision.reason)
