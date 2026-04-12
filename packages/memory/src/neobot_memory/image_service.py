"""Image analysis cache service."""

from __future__ import annotations

from typing import Optional

from neobot_contracts.models.memory import ImageAnalysis
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


class ImageAnalysisService:
    """Service for cached image analysis CRUD and lookup operations."""

    def __init__(self, uow_factory: UnitOfWorkFactory, logger: Logger) -> None:
        self._uow_factory = uow_factory
        self._logger = logger

    async def get(self, file_hash: str) -> Optional[ImageAnalysis]:
        async with self._uow_factory() as uow:
            item = await uow.images.get(file_hash)
        self._logger.debug("image analysis fetched", file_hash=file_hash, found=item is not None)
        return item

    async def exists(self, file_hash: str) -> bool:
        async with self._uow_factory() as uow:
            exists = await uow.images.exists(file_hash)
        self._logger.debug("image analysis existence checked", file_hash=file_hash, exists=exists)
        return exists

    async def list(
        self,
        *,
        source_query: Optional[str] = None,
        has_analysis_text: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageAnalysis]:
        async with self._uow_factory() as uow:
            items = await uow.images.list(
                source_query=source_query,
                has_analysis_text=has_analysis_text,
                limit=limit,
                offset=offset,
            )
        self._logger.debug(
            "image analyses listed",
            count=len(items),
            limit=limit,
            offset=offset,
            has_analysis_text=has_analysis_text,
        )
        return items

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
        async with self._uow_factory() as uow:
            item = await uow.images.set(
                file_hash,
                source=source,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                processed_width=processed_width,
                processed_height=processed_height,
                analysis_text=analysis_text,
            )
            await uow.commit()
        self._logger.debug(
            "image analysis saved",
            file_hash=file_hash,
            version=item.version,
        )
        return item

    async def delete(self, file_hash: str) -> bool:
        async with self._uow_factory() as uow:
            deleted = await uow.images.delete(file_hash)
            if deleted:
                await uow.commit()
        self._logger.debug("image analysis deleted", file_hash=file_hash, deleted=deleted)
        return deleted
