"""SqlAlchemy message repository."""

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
        return [
            IncomingMessage(
                event_id=r.event_id,
                conversation=ConversationRef(kind=r.conversation_kind, id=r.conversation_id),
                sender_id=r.sender_id,
                sender_name=r.sender_name,
                text=r.text,
                occurred_at=r.occurred_at,
            )
            for r in reversed(rows)
        ]
