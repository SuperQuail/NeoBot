"""BotGateway Port — 消息发送抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef


@runtime_checkable
class BotGateway(Protocol):
    """机器人消息网关，上层通过此接口发送消息"""

    async def send_text(self, conversation: ConversationRef, text: str) -> None: ...
    async def send_image(self, conversation: ConversationRef, url: str) -> None: ...


class Subscription(Protocol):
    """事件订阅句柄"""

    def unsubscribe(self) -> None: ...
