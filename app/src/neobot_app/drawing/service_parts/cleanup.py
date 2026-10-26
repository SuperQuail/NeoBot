"""临时文件清理与图库陈旧记录维护。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING



from neobot_app.drawing.config import (
    TMP_SOURCE,
    _IMAGE_EXTENSIONS,
)

if TYPE_CHECKING:
    pass

from ._facade import facade


class CleanupMixin:
    """临时文件清理与图库陈旧记录维护。"""

    async def _cleanup_stale_records(self) -> None:
        """删除数据库中文件已不存在的记录，更新文件已重命名的记录，并对各目录内哈希重复的文件去重（保留最新）。"""
        disk_files: set[str] = set()

        # 逐目录去重：同一目录内哈希相同的文件只保留最新的
        for directory in (self._tmp_dir, self._gallery_dir):
            if not directory.exists():
                continue
            hash_to_files: dict[str, list[Path]] = {}
            for child in directory.iterdir():
                if not child.is_file() or child.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                resolved = str(child.resolve())
                disk_files.add(resolved)
                try:
                    prepared = await facade().prepare_local_image_async(child)
                    hash_to_files.setdefault(prepared.file_hash, []).append(child)
                except Exception:
                    continue

            for file_hash, files in hash_to_files.items():
                if len(files) <= 1:
                    continue
                files.sort(key=lambda f: f.stat().st_mtime)
                keeper = files[-1]
                for dup in files[:-1]:
                    self._logger.info(
                        f"图库去重: 保留较新文件 {keeper.name}，删除重复文件 {dup.name}"
                    )
                    dup.unlink(missing_ok=True)
                    dup.with_suffix(".txt").unlink(missing_ok=True)
                    disk_files.discard(str(dup.resolve()))

        async with self._uow_factory() as uow:
            all_records = await uow.creator_images.list(source=None, limit=99999, offset=0)
            for record in all_records:
                record_path = Path(record.file_path)
                if record_path.exists() and record_path.is_file():
                    resolved = str(record_path.resolve())
                    if resolved != record.file_path:
                        await uow.creator_images.rename(record.image_id, resolved)
                    continue
                resolved = str(record_path.resolve())
                if resolved in disk_files:
                    if resolved != record.file_path:
                        await uow.creator_images.rename(record.image_id, resolved)
                    continue
                self._logger.debug(f"清理失效图库记录: {record.image_id} (文件不存在)")
                await uow.creator_images.delete(record.image_id)
            await uow.commit()

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_stale_records()
                await self._sync_image_sidecars()
                await self._cleanup_expired_tmp_files()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(f"图库定时清理失败: {exc}")

    def _start_cleanup_task(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _stop_cleanup_task(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def cleanup_tmp(self) -> None:
        """删除 tmp 目录中的全部文件，并移除对应的数据库记录。"""
        deleted_count = 0
        if self._tmp_dir.exists():
            for child in self._tmp_dir.iterdir():
                if child.is_file():
                    try:
                        child.unlink()
                        deleted_count += 1
                    except OSError as exc:
                        self._logger.warning(
                            f"删除临时文件失败: {child}",
                            error=str(exc),
                        )

        db_deleted = 0
        try:
            async with self._uow_factory() as uow:
                db_deleted = await uow.creator_images.delete_by_source("tmp")
                await uow.commit()
        except Exception as exc:
            self._logger.warning(
                "清理临时图片数据库记录失败",
                error=str(exc),
            )

        if deleted_count or db_deleted:
            self._logger.info(
                "creator 临时文件已清理",
                deleted_files=deleted_count,
                deleted_records=db_deleted,
            )

    async def _cleanup_expired_tmp_files(self) -> None:
        """删除超过保留时间的临时绘图文件及对应记录。"""
        cutoff = time.time() - self._TMP_MAX_AGE_SECONDS
        expired_ids: list[str] = []
        deleted_files = 0

        async with self._uow_factory() as uow:
            records = await uow.creator_images.list(source=TMP_SOURCE, limit=99999, offset=0)
            for record in records:
                path = Path(record.file_path)
                try:
                    mtime = path.stat().st_mtime if path.exists() else 0.0
                except OSError:
                    mtime = 0.0
                if mtime > cutoff:
                    continue
                if path.exists():
                    try:
                        path.unlink()
                        deleted_files += 1
                    except OSError as exc:
                        self._logger.warning(
                            "删除过期临时图片失败",
                            image_id=record.image_id,
                            path=str(path),
                            error=str(exc),
                        )
                        continue
                try:
                    path.with_suffix(".txt").unlink(missing_ok=True)
                except OSError:
                    pass
                expired_ids.append(record.image_id)

            for image_id in expired_ids:
                await uow.creator_images.delete(image_id)
            await uow.commit()

        if expired_ids or deleted_files:
            self._logger.info(
                "creator 过期临时图片已清理",
                deleted_files=deleted_files,
                deleted_records=len(expired_ids),
                max_age_hours=self._TMP_MAX_AGE_SECONDS // 3600,
            )

