"""SqlAlchemy creator image repository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sql_delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.memory import CreatorImageRecord
from neobot_contracts.time_context import now_utc, to_utc
from neobot_contracts.ports.creator_image_access import CreatorImageAccess

from neobot_storage.models import CreatorImageData


class SqlAlchemyCreatorImageAccess:
    """SqlAlchemy implementation of CreatorImageAccess protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: str) -> Optional[CreatorImageRecord]:
        row = await self._get_optional_row(image_id)
        if row is None:
            return None
        return self._to_domain(row)

    async def get_by_hash(self, file_hash: str) -> Optional[CreatorImageRecord]:
        stmt = select(CreatorImageData).where(CreatorImageData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        return self._to_domain(row)

    async def set(
        self,
        image_id: str,
        *,
        source: str,
        file_hash: str,
        file_path: str,
        prompt: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        image_source: Optional[str] = None,
    ) -> CreatorImageRecord:
        now = now_utc()

        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            stmt = sqlite_insert(CreatorImageData).values(
                image_id=image_id,
                source=source,
                file_hash=file_hash,
                file_path=file_path,
                prompt=prompt,
                description=description,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                image_source=image_source,
                created_at=now,
                updated_at=now,
                version=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["image_id"],
                set_={
                    "source": source,
                    "file_hash": file_hash,
                    "file_path": file_path,
                    "prompt": prompt,
                    "description": description,
                    "mime_type": mime_type,
                    "original_width": original_width,
                    "original_height": original_height,
                    "image_source": image_source,
                    "updated_at": now,
                    "version": CreatorImageData.version + 1,
                },
            )
            await self._session.execute(stmt)
            row = await self._get_row(image_id)
        else:
            row = await self._get_optional_row(image_id)
            if row is None:
                row = CreatorImageData(
                    image_id=image_id,
                    source=source,
                    file_hash=file_hash,
                    file_path=file_path,
                    prompt=prompt,
                    description=description,
                    mime_type=mime_type,
                    original_width=original_width,
                    original_height=original_height,
                    image_source=image_source,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
                self._session.add(row)
            else:
                row.source = source
                row.file_hash = file_hash
                row.file_path = file_path
                row.prompt = prompt
                row.description = description
                row.mime_type = mime_type
                row.original_width = original_width
                row.original_height = original_height
                row.image_source = image_source
                row.updated_at = now
                row.version += 1

        await self._session.flush()
        return self._to_domain(row)

    async def delete(self, image_id: str) -> bool:
        row = await self._get_optional_row(image_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def delete_by_source(self, source: str) -> int:
        stmt = sql_delete(CreatorImageData).where(CreatorImageData.source == source)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def rename(self, image_id: str, new_file_path: str) -> CreatorImageRecord:
        row = await self._get_optional_row(image_id)
        if row is None:
            raise LookupError(f"creator image not found for image_id={image_id}")
        row.file_path = new_file_path
        row.updated_at = now_utc()
        row.version += 1
        await self._session.flush()
        return self._to_domain(row)

    async def count(self, *, source: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(CreatorImageData)
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list(
        self,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        stmt = select(CreatorImageData)
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        stmt = (
            stmt.order_by(CreatorImageData.updated_at.desc(), CreatorImageData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def search(
        self,
        keyword: str,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        pattern = f"%{keyword}%"
        stmt = select(CreatorImageData).where(
            or_(
                CreatorImageData.description.like(pattern),
                CreatorImageData.prompt.like(pattern),
            )
        )
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        stmt = (
            stmt.order_by(CreatorImageData.updated_at.desc(), CreatorImageData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def _get_optional_row(self, image_id: str) -> Optional[CreatorImageData]:
        stmt = select(CreatorImageData).where(CreatorImageData.image_id == image_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, image_id: str) -> CreatorImageData:
        row = await self._get_optional_row(image_id)
        if row is None:
            raise LookupError(f"creator image entry not found for image_id={image_id}")
        return row

    @staticmethod
    def _to_domain(row: CreatorImageData) -> CreatorImageRecord:
        return CreatorImageRecord(
            id=row.id,
            image_id=row.image_id,
            source=row.source,
            file_hash=row.file_hash,
            file_path=row.file_path,
            prompt=row.prompt,
            description=row.description,
            mime_type=row.mime_type,
            original_width=row.original_width,
            original_height=row.original_height,
            created_at=SqlAlchemyCreatorImageAccess._normalize_datetime(row.created_at),
            updated_at=SqlAlchemyCreatorImageAccess._normalize_datetime(row.updated_at),
            version=row.version,
            image_source=row.image_source,
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        return to_utc(value)


_: CreatorImageAccess = SqlAlchemyCreatorImageAccess  # type: ignore
