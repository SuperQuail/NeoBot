"""SqlAlchemy emoji analysis repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.memory import EmojiRecord
from neobot_contracts.ports.emoji_access import EmojiAccess

from neobot_storage.models import EmojiData


class SqlAlchemyEmojiAccess:
    """SqlAlchemy implementation of EmojiAccess protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, file_hash: str) -> Optional[EmojiRecord]:
        stmt = select(EmojiData).where(EmojiData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def get_by_file_name(self, file_name: str) -> Optional[EmojiRecord]:
        stmt = select(EmojiData).where(EmojiData.file_name == file_name)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def set(
        self,
        file_hash: str,
        *,
        file_name: str,
        file_path: str,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        analysis_text: Optional[str] = None,
    ) -> EmojiRecord:
        now = datetime.now(timezone.utc)

        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            stmt = sqlite_insert(EmojiData).values(
                file_hash=file_hash,
                file_name=file_name,
                file_path=file_path,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                analysis_text=analysis_text,
                created_at=now,
                updated_at=now,
                version=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["file_hash"],
                set_={
                    "file_name": file_name,
                    "file_path": file_path,
                    "mime_type": mime_type,
                    "original_width": original_width,
                    "original_height": original_height,
                    "analysis_text": analysis_text,
                    "updated_at": now,
                    "version": EmojiData.version + 1,
                },
            )
            await self._session.execute(stmt)
            await self._session.flush()
            row = await self._get_row(file_hash)
            return self._to_domain(row)

        row = await self._get_optional_row(file_hash)
        if row is None:
            row = EmojiData(
                file_hash=file_hash,
                file_name=file_name,
                file_path=file_path,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                analysis_text=analysis_text,
                created_at=now,
                updated_at=now,
                version=1,
            )
            self._session.add(row)
        else:
            row.file_name = file_name
            row.file_path = file_path
            row.mime_type = mime_type
            row.original_width = original_width
            row.original_height = original_height
            row.analysis_text = analysis_text
            row.updated_at = now
            row.version += 1

        await self._session.flush()
        return self._to_domain(row)

    async def delete(self, file_hash: str) -> bool:
        row = await self._get_optional_row(file_hash)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_all(self) -> list[EmojiRecord]:
        stmt = select(EmojiData).order_by(EmojiData.file_name)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_domain(row) for row in rows]

    async def _get_optional_row(self, file_hash: str) -> Optional[EmojiData]:
        stmt = select(EmojiData).where(EmojiData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, file_hash: str) -> EmojiData:
        row = await self._get_optional_row(file_hash)
        if row is None:
            raise LookupError(f"emoji entry not found for hash={file_hash}")
        return row

    @staticmethod
    def _to_domain(row: EmojiData) -> EmojiRecord:
        return EmojiRecord(
            id=row.id,
            file_hash=row.file_hash,
            file_name=row.file_name,
            file_path=row.file_path,
            mime_type=row.mime_type,
            original_width=row.original_width,
            original_height=row.original_height,
            analysis_text=row.analysis_text,
            created_at=SqlAlchemyEmojiAccess._normalize_datetime(row.created_at),
            updated_at=SqlAlchemyEmojiAccess._normalize_datetime(row.updated_at),
            version=row.version,
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


_: EmojiAccess = SqlAlchemyEmojiAccess  # type: ignore
