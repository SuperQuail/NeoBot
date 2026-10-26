"""表情包导入、改名、改描述与删除（由 service.py 拆分）。"""

from __future__ import annotations

import hashlib

from neobot_app.message.image_pipeline import prepare_local_image_async
from neobot_contracts.models.memory import EmojiRecord

from neobot_app.emoji.service_parts.models import (
    EmojiDuplicateError,
    EmojiEntry,
    EmojiImportResult,
    _detect_image_suffix,
    _safe_emoji_file_name,
)


class _MutationMixin:
    async def add_image_bytes(
        self,
        image_bytes: bytes,
        *,
        file_name: str | None = None,
        analysis_text: str | None = None,
        image_source: str | None = None,
    ) -> EmojiImportResult:
        """向表情文件夹添加一张图片文件，并刷新内存索引。"""
        if not image_bytes:
            raise ValueError("图片内容为空")

        self._emoji_dir.mkdir(parents=True, exist_ok=True)

        file_hash = hashlib.sha256(image_bytes).hexdigest()
        async with self._uow_factory() as uow:
            existing = await uow.emojis.get_by_hash(file_hash)
            if existing is not None:
                number = self.find_number_by_hash(file_hash)
                raise EmojiDuplicateError(
                    f"该图片与已有表情包重复（哈希 {file_hash[:12]}…），"
                    f"已有文件: {existing.file_name}，编号 {number}",
                    number=number,
                    file_name=existing.file_name,
                    analysis_text=existing.analysis_text or "",
                )

        suffix = _detect_image_suffix(image_bytes)
        target_name = _safe_emoji_file_name(file_name, suffix)
        target_path = self._emoji_dir / target_name
        while target_path.exists():
            from uuid import uuid4
            target_name = f"emoji_{uuid4().hex[:12]}.{suffix}"
            target_path = self._emoji_dir / target_name

        target_path.write_bytes(image_bytes)

        text = (analysis_text or "").strip()
        if text:
            target_path.with_suffix(".txt").write_text(text, encoding="utf-8")
            prepared = await prepare_local_image_async(target_path)
            async with self._uow_factory() as uow:
                await uow.emojis.set(
                    prepared.file_hash,
                    file_name=target_path.name,
                    file_path=str(target_path.relative_to(self._emoji_dir)),
                    mime_type=prepared.mime_type,
                    original_width=prepared.original_width,
                    original_height=prepared.original_height,
                    analysis_text=text,
                    image_source=image_source,
                )
                await uow.commit()

        await self._scan_folder()
        for number, entry in self.list_entries():
            if entry.file_path == target_path:
                return EmojiImportResult(number=number, entry=entry)
        raise LookupError(f"表情包已写入但未能建立编号: {target_path.name}")

    async def delete_entry(self, number: int) -> bool:
        entry = self.get_entry(number)
        if entry is None:
            return False

        file_hash: str | None = None
        try:
            file_hash = (await prepare_local_image_async(entry.file_path)).file_hash
        except Exception as exc:
            self._logger.warning(f"计算表情包哈希失败 {entry.file_name}: {exc}")

        if file_hash:
            try:
                async with self._uow_factory() as uow:
                    await uow.emojis.delete(file_hash)
                    await uow.commit()
            except Exception as exc:
                self._logger.warning(f"删除表情包数据库记录失败 {entry.file_name}: {exc}")

        entry.file_path.unlink(missing_ok=True)
        entry.file_path.with_suffix(".txt").unlink(missing_ok=True)
        await self._scan_folder()
        return True

    async def update_entry_description(self, number: int, analysis_text: str) -> EmojiEntry:
        text = analysis_text.strip()
        if not text:
            raise ValueError("表情包描述不能为空")
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists() or not entry.file_path.is_file():
            raise FileNotFoundError(f"表情包文件不存在: {entry.file_path}")

        entry.file_path.with_suffix(".txt").write_text(text, encoding="utf-8")
        prepared = await prepare_local_image_async(entry.file_path)
        async with self._uow_factory() as uow:
            await uow.emojis.set(
                prepared.file_hash,
                file_name=entry.file_name,
                file_path=str(entry.file_path.relative_to(self._emoji_dir)),
                mime_type=prepared.mime_type,
                original_width=prepared.original_width,
                original_height=prepared.original_height,
                analysis_text=text,
                image_source=entry.image_source,
            )
            await uow.commit()

        await self._scan_folder()
        refreshed = self.get_entry(number)
        if refreshed is not None:
            return refreshed
        return EmojiEntry(
            file_name=entry.file_name,
            file_path=entry.file_path,
            analysis_text=text,
            file_hash=entry.file_hash,
            image_source=entry.image_source,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            exposure_score=entry.exposure_score,
            is_favorite=entry.is_favorite,
        )

    async def update_emoji_source(self, number: int, image_source: str) -> EmojiRecord | None:
        """更新表情包的图片来源。"""
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists():
            raise LookupError(f"表情包文件不存在: {entry.file_path}")

        prepared = await prepare_local_image_async(entry.file_path)
        async with self._uow_factory() as uow:
            result = await uow.emojis.set(
                prepared.file_hash,
                file_name=entry.file_name,
                file_path=str(entry.file_path.relative_to(self._emoji_dir)),
                mime_type=prepared.mime_type,
                original_width=prepared.original_width,
                original_height=prepared.original_height,
                analysis_text=entry.analysis_text or "",
                image_source=image_source,
            )
            await uow.commit()
            return result

    async def rename_entry(self, number: int, new_name: str) -> EmojiEntry:
        """重命名表情包文件、txt 侧文件并更新数据库。"""
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists() or not entry.file_path.is_file():
            raise FileNotFoundError(f"表情包文件不存在: {entry.file_path}")

        safe_name = _safe_emoji_file_name(new_name, entry.file_path.suffix)
        new_path = self._emoji_dir / safe_name

        old_resolved = entry.file_path.resolve()
        new_resolved = new_path.resolve()
        if old_resolved == new_resolved:
            return entry

        if new_path.exists():
            raise FileExistsError(f"目标文件名已存在: {safe_name}")

        old_path = entry.file_path
        old_path.rename(new_path)
        old_txt = old_path.with_suffix(".txt")
        new_txt = new_path.with_suffix(".txt")
        if old_txt.exists():
            old_txt.rename(new_txt)

        prepared = await prepare_local_image_async(new_path)
        try:
            async with self._uow_factory() as uow:
                renamed = await uow.emojis.rename(
                    prepared.file_hash,
                    new_file_name=safe_name,
                    new_file_path=str(new_path.relative_to(self._emoji_dir)),
                )
                await uow.commit()
        except Exception:
            new_path.rename(old_path)
            if new_txt.exists():
                new_txt.rename(old_txt)
            raise

        updated = EmojiEntry(
            file_name=safe_name,
            file_path=new_path,
            analysis_text=entry.analysis_text,
            use_count=renamed.use_count,
            file_hash=renamed.file_hash,
            image_source=renamed.image_source,
            created_at=renamed.created_at,
            updated_at=renamed.updated_at,
            exposure_score=renamed.exposure_score,
            is_favorite=renamed.is_favorite,
        )
        self._entries[number] = updated
        return updated
