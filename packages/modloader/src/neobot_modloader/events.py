"""插件稳定事件视图：保留原始协议，同时提供常用身份和消息访问。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from neobot_modloader.message import Message, MessageChain
from neobot_modloader.users import UserDirectory, UserProfile


@dataclass(frozen=True)
class IncomingEvent:
    """一次入站事件；sender 来自事件本身，不隐式查询网络。"""

    raw: Mapping[str, Any]

    @property
    def kind(self) -> str:
        return str(self.raw.get("post_type") or "")

    @property
    def user_id(self) -> int | None:
        value = self.raw.get("user_id")
        return int(value) if value is not None else None

    @property
    def group_id(self) -> int | None:
        value = self.raw.get("group_id")
        return int(value) if value is not None else None

    @property
    def sender(self) -> UserProfile:
        payload = dict(self.raw)
        payload["sender"] = {"user_id": self.user_id, **dict(payload.get("sender") or {})}
        return UserDirectory.from_event(payload)

    @property
    def message(self) -> Message:
        return Message(self.raw)

    @property
    def chain(self) -> MessageChain:
        return self.message.to_chain()

    @property
    def scope(self) -> tuple[str, str, str, str]:
        """机器人、会话类型、会话和用户共同界定后续消息归属。"""
        kind = str(self.raw.get("message_type") or "")
        conversation = self.group_id if kind == "group" else self.user_id
        return (str(self.raw.get("self_id") or ""), kind, str(conversation), str(self.user_id))
