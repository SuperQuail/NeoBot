"""SqlAlchemy archive memory repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.archive_memory_access import ArchiveMemoryAccess
from neobot_contracts.time_context import now_utc, to_utc

from neobot_storage.models import ArchiveMemoryData


class SqlAlchemyArchiveMemoryAccess:
    """SqlAlchemy implementation of ArchiveMemoryAccess protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, table_name: str, key: str) -> Optional[ArchiveMemory]:
        """Get archive memory entry by table name and key."""
        stmt = select(ArchiveMemoryData).where(
            ArchiveMemoryData.table_name == table_name,
            ArchiveMemoryData.key == key,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            return self._to_domain(row)
        return None

    async def set(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        """Create or update archive memory entry."""
        now = now_utc()
        serialized_tags = self._tags_to_string(tags)

        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            stmt = sqlite_insert(ArchiveMemoryData).values(
                table_name=table_name,
                key=key,
                value=value,
                tags=serialized_tags,
                created_at=now,
                updated_at=now,
                version=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["table_name", "key"],
                set_={
                    "value": value,
                    "tags": serialized_tags,
                    "updated_at": now,
                    "version": ArchiveMemoryData.version + 1,
                },
            )
            await self._session.execute(stmt)
            await self._session.flush()
            row = await self._get_row(table_name, key)
            return self._to_domain(row)

        row = await self._get_optional_row(table_name, key)
        if row:
            row.value = value
            row.tags = serialized_tags
            row.updated_at = now
            row.version += 1
        else:
            row = ArchiveMemoryData(
                table_name=table_name,
                key=key,
                value=value,
                tags=serialized_tags,
                created_at=now,
                updated_at=now,
                version=1,
            )
            self._session.add(row)

        await self._session.flush()
        return self._to_domain(row)

    async def delete(self, table_name: str, key: str) -> bool:
        """Delete archive memory entry."""
        row = await self._get_optional_row(table_name, key)
        if row:
            await self._session.delete(row)
            await self._session.flush()
            return True
        return False

    async def exists(self, table_name: str, key: str) -> bool:
        """Check if archive memory entry exists."""
        stmt = select(ArchiveMemoryData.id).where(
            ArchiveMemoryData.table_name == table_name,
            ArchiveMemoryData.key == key,
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list(
        self,
        table_name: str,
        *,
        tags: Optional[list[str]] = None,
        key_query: Optional[str] = None,
        value_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]:
        """List archive entries for a table with filtering and pagination."""
        stmt = select(ArchiveMemoryData).where(ArchiveMemoryData.table_name == table_name)

        if key_query:
            stmt = stmt.where(ArchiveMemoryData.key.ilike(f"%{key_query}%"))
        if value_query:
            stmt = stmt.where(ArchiveMemoryData.value.ilike(f"%{value_query}%"))
        if tags:
            for tag in tags:
                stmt = stmt.where(ArchiveMemoryData.tags.contains(self._serialize_tag(tag)))

        stmt = (
            stmt.order_by(ArchiveMemoryData.updated_at.desc(), ArchiveMemoryData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_domain(row) for row in rows]

    async def _get_optional_row(self, table_name: str, key: str) -> Optional[ArchiveMemoryData]:
        stmt = select(ArchiveMemoryData).where(
            ArchiveMemoryData.table_name == table_name,
            ArchiveMemoryData.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, table_name: str, key: str) -> ArchiveMemoryData:
        row = await self._get_optional_row(table_name, key)
        if row is None:
            raise LookupError(f"archive entry not found for {table_name}:{key}")
        return row

    def _to_domain(self, row: ArchiveMemoryData) -> ArchiveMemory:
        """Convert SQLAlchemy model to domain model."""
        return ArchiveMemory(
            id=row.id,
            table_name=row.table_name,
            key=row.key,
            value=row.value,
            tags=self._string_to_tags(row.tags),
            created_at=self._normalize_datetime(row.created_at),
            updated_at=self._normalize_datetime(row.updated_at),
            version=row.version,
        )

    @staticmethod
    def _tags_to_string(tags: list[str]) -> str:
        """Convert tags to a reversible serialized string."""
        return json.dumps(tags, ensure_ascii=True)

    @staticmethod
    def _serialize_tag(tag: str) -> str:
        """Serialize a single tag so text filtering matches exact JSON entries."""
        return json.dumps(tag, ensure_ascii=True)

    @staticmethod
    def _string_to_tags(tags_string: Optional[str]) -> list[str]:
        """Convert serialized tags back to a list.

        Falls back to the legacy comma-separated format so existing rows
        remain readable after upgrading the repository implementation.
        """
        if not tags_string:
            return []
        try:
            decoded = json.loads(tags_string)
        except json.JSONDecodeError:
            return SqlAlchemyArchiveMemoryAccess._string_to_legacy_tags(tags_string)

        if isinstance(decoded, list):
            return [str(tag) for tag in decoded]
        if isinstance(decoded, str):
            return SqlAlchemyArchiveMemoryAccess._string_to_legacy_tags(decoded)
        return []

    @staticmethod
    def _string_to_legacy_tags(tags_string: str) -> list[str]:
        """Decode the previous comma-separated tag format."""
        tags = tags_string.split(",")
        return [tag.replace(";", ",") for tag in tags if tag]

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        """Always expose archive timestamps as UTC-aware datetimes."""
        return to_utc(value)


# Type check: ensure class implements the protocol
_: ArchiveMemoryAccess = SqlAlchemyArchiveMemoryAccess  # type: ignore
