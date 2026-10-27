"""图库查询、描述/来源更新与重命名。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING


from neobot_contracts.models.memory import CreatorImageRecord

from neobot_app.drawing.config import (
    GALLERY_SOURCE,
)

if TYPE_CHECKING:
    from neobot_contracts.models.memory import EmojiRecord

from .helpers import _sanitize_filename


class GalleryMixin:
    """图库查询、描述/来源更新与重命名。"""

    async def list_images(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        normalized = self._normalize_source(source) if source else None
        self._start_cleanup_task()
        return await self._list_image_records(source=normalized, limit=limit, offset=offset)

    async def count_images(self, *, source: str | None = None) -> int:
        self._start_cleanup_task()
        async with self._uow_factory() as uow:
            return await uow.creator_images.count(source=source)

    async def search_images(
        self,
        keyword: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        """按关键词搜索图库图片。

        支持多关键词(空格分隔):返回按"命中关键词数"降序排列,
        全部关键词都命中的记录排在最前(角色立绘精确搜索)。
        """
        self._start_cleanup_task()
        limit = limit if limit is not None else self._config.gallery_page_size
        keywords = [part.strip() for part in keyword.split() if part.strip()]
        if not keywords:
            return await self._list_image_records(
                source=source, limit=limit, offset=offset
            )
        if len(keywords) == 1:
            return await self._search_single(keywords[0], source=source, limit=limit, offset=offset)

        # 多关键词:分别查询(扩大候选),按命中词数排序后截断
        fetch_limit = max(limit * 3, 30)
        scored: dict[str, tuple[CreatorImageRecord, int]] = {}
        for index, word in enumerate(keywords):
            records = await self._search_single(word, source=source, limit=fetch_limit)
            for record in records:
                previous = scored.get(record.image_id)
                if previous is None:
                    scored[record.image_id] = (record, 1)
                else:
                    scored[record.image_id] = (previous[0], previous[1] + 1)
        ordered = sorted(
            scored.values(), key=lambda item: (-item[1], item[0].id or 0)
        )
        return [record for record, _count in ordered][offset : offset + limit]

    async def _search_single(
        self,
        keyword: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            records: list[CreatorImageRecord] = await uow.creator_images.search(
                keyword,
                source=source,
                limit=limit,
                offset=offset,
            )
        return [record for record in records if Path(record.file_path).is_file()]

    async def _list_image_records(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            records = await uow.creator_images.list(source=source, limit=limit, offset=offset)
        return [record for record in records if Path(record.file_path).is_file()]

    async def gallery_add(
        self, *, image_id: str, description: str | None = None, name: str | None = None
    ) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        source = await self._get_existing(image_id)
        if source is None:
            raise LookupError(f"图片 {image_id} 不存在")
        if source.source == GALLERY_SOURCE:
            return source
        await self._ensure_gallery_capacity()
        target_id = self._new_image_id(GALLERY_SOURCE)
        target_path = self._copy_to_gallery(source.file_path, target_id)
        record = await self._upsert_record(
            target_id,
            source=GALLERY_SOURCE,
            file_path=target_path,
            prompt=source.prompt,
            description=description or source.description,
            image_source=source.image_source,
        )
        if name:
            safe_name = _sanitize_filename(name)
            if safe_name:
                record = await self.gallery_rename(image_id=target_id, new_name=safe_name)
        return record

    async def gallery_replace(self, *, target_id: str, source_id: str) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        target = await self._get_existing(target_id)
        if target is None or target.source != GALLERY_SOURCE:
            raise LookupError(f"图库图片 {target_id} 不存在")
        source = await self._get_existing(source_id)
        if source is None:
            raise LookupError(f"来源图片 {source_id} 不存在")
        target_path = Path(target.file_path)
        target_path.write_bytes(Path(source.file_path).read_bytes())
        return await self._upsert_record(
            target.image_id,
            source=GALLERY_SOURCE,
            file_path=target_path,
            prompt=source.prompt,
            description=target.description or source.description,
        )

    async def update_image_description(
        self, *, image_id: str, description: str
    ) -> CreatorImageRecord:
        text = description.strip()
        if not text:
            raise ValueError("图片描述不能为空")
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        file_path = Path(record.file_path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {file_path}")
        return await self._upsert_record(
            record.image_id,
            source=record.source,
            file_path=file_path,
            prompt=record.prompt,
            description=text,
        )

    async def gallery_delete(self, *, image_id: str) -> bool:
        self._ensure_gallery_enabled()
        record = await self._get_existing(image_id)
        if record is None or record.source != GALLERY_SOURCE:
            return False
        async with self._uow_factory() as uow:
            deleted = await uow.creator_images.delete(image_id)
            await uow.commit()
        if deleted:
            Path(record.file_path).unlink(missing_ok=True)
            Path(record.file_path).with_suffix(".txt").unlink(missing_ok=True)
        return deleted

    async def update_image_source(self, image_id: str, image_source: str) -> CreatorImageRecord:
        """更新图库/暂存区图片的图片来源。"""
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        file_path = Path(record.file_path)
        return await self._upsert_record(
            record.image_id,
            source=record.source,
            file_path=file_path,
            prompt=record.prompt,
            description=record.description,
            image_source=image_source,
        )

    async def update_emoji_source(self, number: int, image_source: str) -> EmojiRecord | None:
        """更新表情包的图片来源。"""
        if self._emoji_service is None:
            return None
        return await self._emoji_service.update_emoji_source(number, image_source)

    async def gallery_rename(
        self, *, image_id: str, new_name: str
    ) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        if record.source != GALLERY_SOURCE:
            raise ValueError(f"只能重命名图库图片，{image_id} 来源为 {record.source}")

        old_path = Path(record.file_path)
        if not old_path.exists() or not old_path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {old_path}")

        safe_name = _sanitize_filename(new_name)
        if not safe_name:
            raise ValueError("新名称无效（清理后为空）")

        suffix = old_path.suffix
        new_path = old_path.parent / f"{safe_name}{suffix}"

        old_resolved = old_path.resolve()
        new_resolved = new_path.resolve()
        if old_resolved == new_resolved:
            return record

        if new_path.exists():
            raise FileExistsError(f"目标文件名已存在: {new_path.name}")

        old_path.rename(new_path)
        old_txt = old_path.with_suffix(".txt")
        new_txt = new_path.with_suffix(".txt")
        if old_txt.exists():
            old_txt.rename(new_txt)

        try:
            async with self._uow_factory() as uow:
                renamed = await uow.creator_images.rename(image_id, str(new_path))
                await uow.commit()
        except Exception:
            new_path.rename(old_path)
            if new_txt.exists():
                new_txt.rename(old_txt)
            raise

        return renamed

