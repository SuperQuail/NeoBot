"""SqlAlchemy 档案压缩快照仓库（spec(4) Part C / D15）。

只服务「压缩前留痕」这一个用途：写入一行、按 (table_name, key) 倒序列举、
查看某一份全文、删除某一份、按保留策略清理。对上层只暴露字典，
避免为一个纯留痕表新增 contracts 领域模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.time_context import now_utc, to_utc

from neobot_storage.models import ArchiveSnapshotData

#: 同一 (table_name, key) 默认保留的快照份数（spec(4) §4.10.4 / D15）。
DEFAULT_SNAPSHOTS_PER_KEY = 10
#: 全局兜底上限：防止大量不同 key 的快照无限累积。
DEFAULT_MAX_SNAPSHOTS = 2000


class SqlAlchemyArchiveSnapshotAccess:
    """压缩前档案快照的 SqlAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        table_name: str,
        key: str,
        value: str,
        *,
        total_chars: int = 0,
        version: int = 0,
        reason: str = "manual",
        operator_ip: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """写入一份快照并返回它的可读投影（含 id）。"""
        row = ArchiveSnapshotData(
            table_name=str(table_name),
            key=str(key),
            value=str(value or ""),
            total_chars=int(total_chars),
            version=int(version),
            reason=str(reason or "manual"),
            operator_ip=(str(operator_ip) if operator_ip else None),
            created_at=created_at or now_utc(),
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_dict(row, include_value=True)

    async def list(
        self,
        table_name: str,
        key: str,
        *,
        limit: int = DEFAULT_SNAPSHOTS_PER_KEY,
        include_value: bool = False,
    ) -> list[dict[str, Any]]:
        """按创建时间倒序列出某条档案的快照（默认不含全文）。"""
        stmt = (
            select(ArchiveSnapshotData)
            .where(
                ArchiveSnapshotData.table_name == str(table_name),
                ArchiveSnapshotData.key == str(key),
            )
            .order_by(ArchiveSnapshotData.created_at.desc(), ArchiveSnapshotData.id.desc())
            .limit(max(0, int(limit)))
        )
        result = await self._session.execute(stmt)
        return [self._to_dict(row, include_value=include_value) for row in result.scalars().all()]

    async def get(self, snapshot_id: int) -> Optional[dict[str, Any]]:
        """读取某一份快照（含全文）。"""
        row = await self._session.get(ArchiveSnapshotData, int(snapshot_id))
        if row is None:
            return None
        return self._to_dict(row, include_value=True)

    async def delete(self, snapshot_id: int) -> bool:
        """删除某一份快照（压缩失败 / 未达标时回滚留痕）。"""
        result = await self._session.execute(
            delete(ArchiveSnapshotData).where(ArchiveSnapshotData.id == int(snapshot_id))
        )
        await self._session.flush()
        return bool(result.rowcount)

    async def prune(
        self,
        table_name: Optional[str] = None,
        key: Optional[str] = None,
        *,
        keep: int = DEFAULT_SNAPSHOTS_PER_KEY,
        max_total: int = DEFAULT_MAX_SNAPSHOTS,
    ) -> int:
        """按保留策略淘汰旧快照，返回删除行数。

        两级：同一 (table_name, key) 只保留最近 ``keep`` 份；全表再兜底保留
        最近 ``max_total`` 份（删除按 created_at/id 倒序取尾，即先删最旧的）。
        只给 max_total 而不给 table_name/key 时只做全局兜底。
        """
        removed = 0
        if table_name and key:
            removed += await self._delete_beyond(
                keep,
                where=(
                    ArchiveSnapshotData.table_name == str(table_name),
                    ArchiveSnapshotData.key == str(key),
                ),
            )
        removed += await self._delete_beyond(max_total, where=())
        return removed

    async def _delete_beyond(self, keep: int, *, where: tuple[Any, ...]) -> int:
        """删除排序后第 keep 名之后的快照（created_at/id 倒序 → 越旧越靠后）。"""
        if int(keep) < 0:
            return 0
        stmt = select(ArchiveSnapshotData.id).order_by(
            ArchiveSnapshotData.created_at.desc(), ArchiveSnapshotData.id.desc()
        )
        if where:
            stmt = stmt.where(*where)
        stmt = stmt.offset(int(keep))
        result = await self._session.execute(stmt)
        stale = [int(value) for value in result.scalars().all()]
        if not stale:
            return 0
        await self._session.execute(
            delete(ArchiveSnapshotData).where(ArchiveSnapshotData.id.in_(stale))
        )
        await self._session.flush()
        return len(stale)

    async def count(self) -> int:
        """快照总行数（测试与运维用）。"""
        result = await self._session.execute(select(func.count(ArchiveSnapshotData.id)))
        return int(result.scalar_one() or 0)

    @staticmethod
    def _to_dict(row: ArchiveSnapshotData, *, include_value: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": int(row.id),
            "table_name": str(row.table_name),
            "key": str(row.key),
            "total_chars": int(row.total_chars or 0),
            "version": int(row.version or 0),
            "reason": str(row.reason or ""),
            "operator_ip": row.operator_ip,
            "created_at": to_utc(row.created_at) if row.created_at else None,
        }
        if include_value:
            payload["value"] = str(row.value or "")
        return payload
