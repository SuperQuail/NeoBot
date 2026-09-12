"""SqlAlchemy 消息仓库。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models import ConversationRef, IncomingMessage

from neobot_storage.models import MessageData


class SqlAlchemyMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_message(self, message: IncomingMessage) -> None:
        row = MessageData(
            event_id=message.event_id,
            conversation_kind=message.conversation.kind,
            conversation_id=message.conversation.id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            text=message.text,
            occurred_at=message.occurred_at,
        )
        self._session.add(row)

    async def get_history(
        self, conversation: ConversationRef, limit: int = 50
    ) -> list[IncomingMessage]:
        stmt = (
            select(MessageData)
            .where(
                MessageData.conversation_kind == conversation.kind,
                MessageData.conversation_id == conversation.id,
            )
            .order_by(MessageData.occurred_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_message(r) for r in reversed(rows)]

    async def get_recent_by_sender(
        self, conversation: ConversationRef, sender_id: str, limit: int = 20
    ) -> list[IncomingMessage]:
        """取该会话内某个发送者最近的若干条消息（按时间正序返回）。

        用于软重启/冷启动后从本地记录补齐 Bot 自身发言（assistant 块）：
        只看「最近 N 条消息」不够——那 N 条可能全是用户消息，必须按发送者过滤。
        """
        stmt = (
            select(MessageData)
            .where(
                MessageData.conversation_kind == conversation.kind,
                MessageData.conversation_id == conversation.id,
                MessageData.sender_id == sender_id,
            )
            .order_by(MessageData.occurred_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_message(r) for r in reversed(rows)]


def _row_to_message(row: MessageData) -> IncomingMessage:
    """ORM 行 -> 领域消息。"""
    return IncomingMessage(
        event_id=row.event_id,
        conversation=ConversationRef(kind=row.conversation_kind, id=row.conversation_id),
        sender_id=row.sender_id,
        sender_name=row.sender_name,
        text=row.text,
        occurred_at=row.occurred_at,
    )
