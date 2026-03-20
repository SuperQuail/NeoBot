"""OneBotGateway — BotGateway Port 的 OneBot 实现"""

from __future__ import annotations

from typing import TYPE_CHECKING

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.gateway import BotGateway

if TYPE_CHECKING:
    from neobot_adapter.adapter import OneBotAdapter


class OneBotGateway:
    """通过 OneBotAdapter 实现 BotGateway，向私聊或群聊发送消息"""

    def __init__(self, adapter: OneBotAdapter) -> None:
        self._adapter = adapter

    async def send_text(self, conversation: ConversationRef, text: str) -> None:
        if conversation.kind == "private":
            await self._adapter.send_private_msg(user_id=int(conversation.id), message=text)
        else:
            await self._adapter.send_group_msg(group_id=int(conversation.id), message=text)

    async def send_image(self, conversation: ConversationRef, url: str) -> None:
        cq = f"[CQ:image,file={url}]"
        if conversation.kind == "private":
            await self._adapter.send_private_msg(user_id=int(conversation.id), message=cq)
        else:
            await self._adapter.send_group_msg(group_id=int(conversation.id), message=cq)
