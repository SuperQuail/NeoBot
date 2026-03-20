"""OneBot 原始事件 → 领域模型映射"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neobot_contracts.models import ConversationRef, IncomingMessage


def map_to_incoming_message(raw_event: dict[str, Any]) -> IncomingMessage:
    """将 OneBot 原始消息事件转换为 IncomingMessage

    支持 post_type == "message" 的私聊和群聊事件

    Args:
        raw_event: OneBot 协议原始事件字典

    Returns:
        协议无关的 IncomingMessage 实例

    Raises:
        ValueError: 如果事件不是受支持的消息类型
    """
    if raw_event.get("post_type") != "message":
        raise ValueError(f"不支持的 post_type: {raw_event.get('post_type')!r}")

    message_type = raw_event.get("message_type")
    if message_type == "private":
        conversation = ConversationRef(kind="private", id=str(raw_event["user_id"]))
    elif message_type == "group":
        conversation = ConversationRef(kind="group", id=str(raw_event["group_id"]))
    else:
        raise ValueError(f"不支持的 message_type: {message_type!r}")

    sender = raw_event.get("sender", {})
    sender_name = (
        sender.get("card")
        or sender.get("nickname")
        or str(raw_event.get("user_id", ""))
    )

    occurred_at = datetime.fromtimestamp(
        int(raw_event.get("time", 0)), tz=timezone.utc
    )

    return IncomingMessage(
        event_id=str(raw_event.get("message_id", "")),
        conversation=conversation,
        sender_id=str(raw_event.get("user_id", "")),
        sender_name=sender_name,
        text=str(raw_event.get("raw_message", raw_event.get("message", ""))),
        occurred_at=occurred_at,
        raw_payload=raw_event,
    )
