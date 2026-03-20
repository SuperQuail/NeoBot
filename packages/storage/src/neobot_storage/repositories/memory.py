"""SqlAlchemy memory repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models import ConversationRef, MemoryRecord

from neobot_storage.models import MemoryData


class SqlAlchemyMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, record: MemoryRecord) -> None:
        row = MemoryData(
            conversation_kind=record.conversation.kind,
            conversation_id=record.conversation.id,
            speaker_id=record.speaker_id,
            content=record.content,
            created_at=record.created_at,
        )
        self._session.add(row)

    async def search(
        self, conversation: ConversationRef, query: str, limit: int = 5
    ) -> list[MemoryRecord]:
        stmt = (
            select(MemoryData)
            .where(
                MemoryData.conversation_kind == conversation.kind,
                MemoryData.conversation_id == conversation.id,
                MemoryData.content.contains(query),
            )
            .order_by(MemoryData.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            MemoryRecord(
                conversation=ConversationRef(kind=r.conversation_kind, id=r.conversation_id),
                speaker_id=r.speaker_id,
                content=r.content,
                created_at=r.created_at,
            )
            for r in rows
        ]
