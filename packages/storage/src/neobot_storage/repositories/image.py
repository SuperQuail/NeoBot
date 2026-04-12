"""SqlAlchemy image analysis repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.memory import ImageAnalysis
from neobot_contracts.ports.image_analysis_access import ImageAnalysisAccess

from neobot_storage.models import ImageAnalysisData


class SqlAlchemyImageAnalysisAccess:
    """SqlAlchemy implementation of ImageAnalysisAccess protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, file_hash: str) -> Optional[ImageAnalysis]:
        stmt = select(ImageAnalysisData).where(ImageAnalysisData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def set(
        self,
        file_hash: str,
        *,
        source: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        processed_width: Optional[int] = None,
        processed_height: Optional[int] = None,
        analysis_text: Optional[str] = None,
    ) -> ImageAnalysis:
        now = datetime.now(timezone.utc)

        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            stmt = sqlite_insert(ImageAnalysisData).values(
                file_hash=file_hash,
                source=source,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                processed_width=processed_width,
                processed_height=processed_height,
                analysis_text=analysis_text,
                created_at=now,
                updated_at=now,
                version=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["file_hash"],
                set_={
                    "source": source,
                    "mime_type": mime_type,
                    "original_width": original_width,
                    "original_height": original_height,
                    "processed_width": processed_width,
                    "processed_height": processed_height,
                    "analysis_text": analysis_text,
                    "updated_at": now,
                    "version": ImageAnalysisData.version + 1,
                },
            )
            await self._session.execute(stmt)
            await self._session.flush()
            row = await self._get_row(file_hash)
            return self._to_domain(row)

        row = await self._get_optional_row(file_hash)
        if row is None:
            row = ImageAnalysisData(
                file_hash=file_hash,
                source=source,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                processed_width=processed_width,
                processed_height=processed_height,
                analysis_text=analysis_text,
                created_at=now,
                updated_at=now,
                version=1,
            )
            self._session.add(row)
        else:
            row.source = source
            row.mime_type = mime_type
            row.original_width = original_width
            row.original_height = original_height
            row.processed_width = processed_width
            row.processed_height = processed_height
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

    async def exists(self, file_hash: str) -> bool:
        stmt = select(ImageAnalysisData.id).where(ImageAnalysisData.file_hash == file_hash).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list(
        self,
        *,
        source_query: Optional[str] = None,
        has_analysis_text: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageAnalysis]:
        stmt = select(ImageAnalysisData)

        if source_query:
            stmt = stmt.where(ImageAnalysisData.source.ilike(f"%{source_query}%"))
        if has_analysis_text is True:
            stmt = stmt.where(ImageAnalysisData.analysis_text.is_not(None))
            stmt = stmt.where(ImageAnalysisData.analysis_text != "")
        elif has_analysis_text is False:
            stmt = stmt.where(
                (ImageAnalysisData.analysis_text.is_(None)) | (ImageAnalysisData.analysis_text == "")
            )

        stmt = (
            stmt.order_by(ImageAnalysisData.updated_at.desc(), ImageAnalysisData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_domain(row) for row in rows]

    async def _get_optional_row(self, file_hash: str) -> Optional[ImageAnalysisData]:
        stmt = select(ImageAnalysisData).where(ImageAnalysisData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, file_hash: str) -> ImageAnalysisData:
        row = await self._get_optional_row(file_hash)
        if row is None:
            raise LookupError(f"image analysis entry not found for hash={file_hash}")
        return row

    @staticmethod
    def _to_domain(row: ImageAnalysisData) -> ImageAnalysis:
        return ImageAnalysis(
            id=row.id,
            file_hash=row.file_hash,
            source=row.source,
            mime_type=row.mime_type,
            original_width=row.original_width,
            original_height=row.original_height,
            processed_width=row.processed_width,
            processed_height=row.processed_height,
            analysis_text=row.analysis_text,
            created_at=SqlAlchemyImageAnalysisAccess._normalize_datetime(row.created_at),
            updated_at=SqlAlchemyImageAnalysisAccess._normalize_datetime(row.updated_at),
            version=row.version,
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


_: ImageAnalysisAccess = SqlAlchemyImageAnalysisAccess  # type: ignore
