"""Outbound API classification and enforcement at the transport boundary."""

from __future__ import annotations

from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.speaking import SpeakingPolicy, SpeechBlocked


def check_speech(policy: SpeakingPolicy | None, conversation: ConversationRef, logger: Any) -> None:
    if policy is None:
        return
    decision = policy.evaluate(conversation)
    if not decision.allowed:
        logger.info(
            "发言策略拒绝发送",
            conversation_kind=conversation.kind,
            conversation_id=conversation.id,
            reason=decision.reason,
        )
        raise SpeechBlocked(decision.reason)


def check_action(policy: SpeakingPolicy | None, action: str, params: dict[str, Any], logger: Any) -> None:
    if policy is None:
        return
    # A like/sign/admin operation is not a message. Only message/media sends
    # with an identifiable destination participate in speech policy.
    action = action.removesuffix("_async")
    kind = None
    if action == "send_msg":
        kind = params.get("message_type")
        if kind not in {"private", "group"}:
            kind = "group" if params.get("group_id") is not None else "private"
    elif action.startswith("send_group_") and action not in {"send_group_sign"}:
        kind = "group"
    elif action.startswith("send_private_"):
        kind = "private"
    elif action in {"upload_group_file", "upload_private_file"}:
        kind = "group" if action == "upload_group_file" else "private"
    if kind is None:
        return
    target = params.get("group_id" if kind == "group" else "user_id")
    if target is not None and str(target):
        check_speech(policy, ConversationRef(kind=kind, id=str(target)), logger)
