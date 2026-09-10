from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_storage.models import MaintenanceRunRecord


class SqlAlchemyMaintenanceRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: MaintenanceRunRecord) -> None:
        self._session.add(record)

    async def latest(self, limit: int = 20) -> list[MaintenanceRunRecord]:
        """按 started_at 降序返回最近若干次维护运行记录。"""
        stmt = (
            select(MaintenanceRunRecord)
            .order_by(MaintenanceRunRecord.started_at.desc())
            .limit(max(1, int(limit)))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def last_finished_success(self) -> MaintenanceRunRecord | None:
        """最近一次成功的维护运行(status == "success" 中 started_at 最大的一条)。"""
        stmt = (
            select(MaintenanceRunRecord)
            .where(MaintenanceRunRecord.status == "success")
            .order_by(MaintenanceRunRecord.started_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def last_attempt(self) -> MaintenanceRunRecord | None:
        """最近一次尝试(任意 status 中 started_at 最大的一条)。"""
        stmt = (
            select(MaintenanceRunRecord)
            .order_by(MaintenanceRunRecord.started_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def finish(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: datetime,
        tool_calls: int = 0,
        summary: str | None = None,
        error: str | None = None,
    ) -> bool:
        """结算一条 running 记录；记录不存在时返回 False。

        时间列一律存无时区 UTC（与 ModelUsageRecord.created_at 一致），
        调用方负责在写库前把 aware datetime 归一化。
        """
        record = await self._session.get(MaintenanceRunRecord, run_id)
        if record is None:
            return False
        record.status = status
        record.finished_at = finished_at
        record.tool_calls = int(tool_calls)
        record.summary = summary
        record.error = error
        return True
