"""消息事件取昵称 / 取正文的小工具。"""

from __future__ import annotations

from typing import Any
from neobot_modloader.message import Message


def _sender_name(message: Any) -> str:
    """从消息事件里尽力取昵称（取不到就回落空串）。"""
    sender = getattr(message, "sender", None)
    if sender is None and isinstance(message, dict):
        sender = message.get("sender")
    if sender is None:
        return ""
    if isinstance(sender, dict):
        return str(sender.get("card") or sender.get("nickname") or "")
    return str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "")


def _event_text(event: Any) -> str:
    try:
        return Message(event).to_chain().exclude("at", "reply").plain_text
    except Exception:
        if isinstance(event, dict):
            return str(event.get("raw_message") or "")
        return ""
