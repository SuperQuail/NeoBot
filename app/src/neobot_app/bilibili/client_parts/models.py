"""B站私信消息与会话的数据模型。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .common import _to_int


@dataclass
class BilibiliMessage:
    """B 站私信消息。"""

    talker_id: int
    sender_uid: int
    msg_type: int
    content: str
    timestamp: int
    msg_key: str = ""
    is_self: bool = False

    @property
    def text(self) -> str:
        """纯文本消息的正文；图片等非文本消息返回空串。"""
        if self.msg_type != 1:
            return ""
        try:
            return str(json.loads(self.content).get("content", ""))
        except (ValueError, TypeError, AttributeError):
            return self.content

    @classmethod
    def from_api(cls, raw: Mapping[str, Any], my_uid: int = 0) -> BilibiliMessage:
        content = raw.get("content", "")
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        sender_uid = _to_int(raw.get("sender_uid"))
        talker_id = _to_int(raw.get("receiver_id")) or sender_uid
        message = cls(
            talker_id=talker_id,
            sender_uid=sender_uid,
            msg_type=_to_int(raw.get("msg_type")) or 1,
            content=str(content),
            timestamp=_to_int(raw.get("timestamp")),
        )
        message.is_self = bool(my_uid and sender_uid == my_uid)
        message.msg_key = f"{message.talker_id}_{message.timestamp}_{message.content[:20]}"
        return message



@dataclass
class BilibiliSession:
    """B 站私信会话。"""

    talker_id: int
    last_msg: BilibiliMessage | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> BilibiliSession:
        session = cls(talker_id=_to_int(raw.get("talker_id")))
        last_msg = raw.get("last_msg")
        if isinstance(last_msg, dict) and last_msg:
            session.last_msg = BilibiliMessage.from_api(last_msg)
        return session
