from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
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

    # ------------------------------------------------------------------
    # 面板用量图表：按时间分桶 + 按模型汇总
    # ------------------------------------------------------------------

    @staticmethod
    def _bucket_format(bucket: str) -> str:
        return "%Y-%m-%dT%H:00:00" if bucket == "hour" else "%Y-%m-%d"

    @staticmethod
    def _sum_columns() -> tuple[Any, ...]:
        return (
            func.count().label("calls"),
            func.coalesce(func.sum(ModelUsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.cache_hit_tokens), 0).label(
                "cache_hit_tokens"
            ),
            func.coalesce(func.sum(ModelUsageRecord.cost_cny), 0.0).label("cost_cny"),
        )

    @staticmethod
    def _row_payload(row: Any, *, at: str) -> dict[str, Any]:
        return {
            "at": at,
            "calls": int(row.calls or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "cache_hit_tokens": int(row.cache_hit_tokens or 0),
            "cost_cny": round(float(row.cost_cny or 0.0), 8),
        }

    async def series_since(
        self,
        since: datetime | None = None,
        *,
        bucket: str = "hour",
    ) -> list[dict[str, Any]]:
        """按小时/天汇总用量：金额、输入/输出 Token 与调用次数。"""
        bucket_col = func.strftime(
            self._bucket_format(bucket), ModelUsageRecord.created_at
        ).label("bucket")
        stmt = select(bucket_col, *self._sum_columns())
        if since is not None:
            stmt = stmt.where(ModelUsageRecord.created_at >= since)
        stmt = stmt.group_by(bucket_col).order_by(bucket_col)
        result = await self._session.execute(stmt)
        return [self._row_payload(row, at=str(row.bucket or "")) for row in result]

    async def breakdown_by_model_since(
        self,
        since: datetime | None = None,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """按「供应商 / 模型」汇总用量，金额降序。"""
        stmt = select(
            ModelUsageRecord.model_name,
            ModelUsageRecord.provider_name,
            *self._sum_columns(),
        )
        if since is not None:
            stmt = stmt.where(ModelUsageRecord.created_at >= since)
        stmt = (
            stmt.group_by(ModelUsageRecord.model_name, ModelUsageRecord.provider_name)
            .order_by(func.sum(ModelUsageRecord.cost_cny).desc())
            .limit(max(1, int(limit)))
        )
        result = await self._session.execute(stmt)
        items: list[dict[str, Any]] = []
        for row in result:
            payload = self._row_payload(row, at="")
            payload.pop("at", None)
            payload["model_name"] = str(row.model_name or "")
            payload["provider_name"] = str(row.provider_name or "")
            items.append(payload)
        return items

    async def breakdown_by_module_since(
        self,
        since: datetime | None = None,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """按调用模块汇总用量，金额降序。"""
        stmt = select(ModelUsageRecord.module_name, *self._sum_columns())
        if since is not None:
            stmt = stmt.where(ModelUsageRecord.created_at >= since)
        stmt = (
            stmt.group_by(ModelUsageRecord.module_name)
            .order_by(func.sum(ModelUsageRecord.cost_cny).desc())
            .limit(max(1, int(limit)))
        )
        result = await self._session.execute(stmt)
        items: list[dict[str, Any]] = []
        for row in result:
            payload = self._row_payload(row, at="")
            payload.pop("at", None)
            payload["module_name"] = str(row.module_name or "")
            items.append(payload)
        return items
