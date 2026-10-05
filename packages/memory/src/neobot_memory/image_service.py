"""图片分析缓存服务。"""

from __future__ import annotations

from typing import Optional

from neobot_contracts.models.memory import ImageAnalysis
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


class ImageAnalysisService:
    """图片分析结果的缓存 CRUD 与查询服务。"""

    def __init__(self, uow_factory: UnitOfWorkFactory, logger: Logger) -> None:
        self._uow_factory = uow_factory
        self._logger = logger

    async def get(self, file_hash: str) -> Optional[ImageAnalysis]:
        async with self._uow_factory() as uow:
            item = await uow.images.get(file_hash)
        self._logger.debug("图像分析已获取", file_hash=file_hash, found=item is not None)
        return item

    async def exists(self, file_hash: str) -> bool:
        async with self._uow_factory() as uow:
            exists = await uow.images.exists(file_hash)
        self._logger.debug("图像分析存在检查", file_hash=file_hash, exists=exists)
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
            "图像分析列表已获取",
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
            "图像分析已保存",
            file_hash=file_hash,
            version=item.version,
        )
        return item

    async def remember_ref(self, source_ref: str, analysis_text: str) -> None:
        """记下「图片引用摘要 -> 描述」（图片过期时回显用）。

        纯兜底缓存：写失败只记日志，绝不能反噬解析路径。
        """
        if not source_ref or not analysis_text:
            return
        try:
            async with self._uow_factory() as uow:
                await uow.images.remember_ref(source_ref, analysis_text)
                await uow.commit()
        except Exception as exc:
            self._logger.warning(
                "图片引用索引写入失败（已忽略）",
                source_ref=source_ref,
                error=str(exc),
            )

    async def description_for_ref(self, source_ref: str) -> Optional[str]:
        """按引用摘要取回描述；查不到或查失败都返回 None。"""
        if not source_ref:
            return None
        try:
            async with self._uow_factory() as uow:
                return await uow.images.get_ref_text(source_ref)
        except Exception as exc:
            self._logger.warning(
                "图片引用索引查询失败（已忽略）",
                source_ref=source_ref,
                error=str(exc),
            )
            return None

    async def delete(self, file_hash: str) -> bool:
        async with self._uow_factory() as uow:
            deleted = await uow.images.delete(file_hash)
            if deleted:
                await uow.commit()
        self._logger.debug("图像分析已删除", file_hash=file_hash, deleted=deleted)
        return deleted
