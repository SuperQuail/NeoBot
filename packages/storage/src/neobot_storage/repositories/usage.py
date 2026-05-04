from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_storage.models import ModelUsageRecord


class SqlAlchemyUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: ModelUsageRecord) -> None:
        self._session.add(record)

    async def stats_since(
        self, since: datetime | None = None
    ) -> list[ModelUsageRecord]:
        stmt = select(ModelUsageRecord)
        if since is not None:
            stmt = stmt.where(ModelUsageRecord.created_at >= since)
        stmt = stmt.order_by(ModelUsageRecord.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
