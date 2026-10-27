"""表情包目录扫描、解析与分批入库（由 service.py 拆分）。"""

from __future__ import annotations

import asyncio

from pathlib import Path

from neobot_app.message.image_pipeline import prepare_local_image_async
from neobot_contracts.models.memory import EmojiRecord

from neobot_app.emoji.service_parts.models import _read_sidecar_text


class _ScanningMixin:
    async def _scan_folder(self) -> None:
        """扫描表情包文件夹，并同步 txt、数据库与视觉解析结果。"""
        # 快照必须在「列出文件之前」取：如果扫描期间有新文件写入，列表里没有它，
        # 但扫描结束若用最新目录快照盖章，下一次读取会误判「没有变化」而永久漏掉
        # 这个文件（A 群保存、B 群扫描并发时就是这样丢新表情包的）。
        snapshot_before = self._dir_snapshot()
        if not self._emoji_dir.exists():
            self._logger.warning(f"表情包目录不存在: {self._emoji_dir}")
            with self._disk_sync_lock:
                self._last_dir_snapshot = self._dir_snapshot()
            return

        image_files = self._list_image_files()
        if not image_files:
            self._logger.info("表情包目录为空")
            self._entries.clear()
            with self._disk_sync_lock:
                self._last_dir_snapshot = snapshot_before
            await self._cleanup_stale_emoji_records({})
            return

        hash_to_path: dict[str, Path] = {}
        path_to_hash: dict[Path, str] = {}
        for file_path in image_files:
            try:
                prepared = await prepare_local_image_async(file_path)
                if prepared.file_hash in hash_to_path:
                    existing = hash_to_path[prepared.file_hash]
                    # 保留较旧的文件
                    if file_path.stat().st_mtime < existing.stat().st_mtime:
                        self._logger.info(
                            f"表情包去重: 保留较旧文件 {file_path.name}，删除 {existing.name}"
                        )
                        existing.unlink(missing_ok=True)
                        existing.with_suffix(".txt").unlink(missing_ok=True)
                        hash_to_path[prepared.file_hash] = file_path
                        path_to_hash[file_path] = prepared.file_hash
                        path_to_hash.pop(existing, None)
                    else:
                        self._logger.info(
                            f"表情包去重: 保留较旧文件 {existing.name}，删除 {file_path.name}"
                        )
                        file_path.unlink(missing_ok=True)
                        file_path.with_suffix(".txt").unlink(missing_ok=True)
                else:
                    hash_to_path[prepared.file_hash] = file_path
                    path_to_hash[file_path] = prepared.file_hash
            except Exception as exc:
                self._logger.warning(f"无法读取表情包文件 {file_path.name}: {exc}")

        if not hash_to_path:
            return

        existing: dict[str, str] = {}
        use_counts: dict[str, int] = {}
        records_by_hash: dict[str, EmojiRecord] = {}
        to_parse: list[tuple[str, Path]] = []

        async with self._uow_factory() as uow:
            for file_path in image_files:
                file_hash = path_to_hash.get(file_path)
                if file_hash is None:
                    continue

                prepared = await prepare_local_image_async(file_path)
                txt_text = _read_sidecar_text(file_path)
                try:
                    record = await uow.emojis.get_by_hash(file_hash)
                except Exception as exc:
                    self._logger.error(f"查询表情包数据库失败: {exc}")
                    record = None
                if txt_text:
                    record = await uow.emojis.set(
                        file_hash,
                        file_name=file_path.name,
                        file_path=str(file_path.relative_to(self._emoji_dir)),
                        mime_type=prepared.mime_type,
                        original_width=prepared.original_width,
                        original_height=prepared.original_height,
                        analysis_text=txt_text,
                        image_source=(
                            record.image_source
                            if record is not None and record.image_source
                            else "部署者提供"
                        ),
                    )
                    existing[file_hash] = txt_text
                else:
                    db_text = (
                        (getattr(record, "analysis_text", None) or "").strip()
                        if record
                        else ""
                    )
                    if db_text:
                        file_path.with_suffix(".txt").write_text(
                            db_text,
                            encoding="utf-8",
                        )
                        existing[file_hash] = db_text
                    else:
                        to_parse.append((file_hash, file_path))

                if record is not None:
                    records_by_hash[file_hash] = record
                    use_counts[file_hash] = record.use_count

            await uow.commit()

        if to_parse:
            self._logger.info(f"发现 {len(to_parse)} 个需要解析的表情包，开始并发解析")
            new_results = await self._parse_batch(to_parse)
            try:
                async with self._uow_factory() as uow:
                    for file_hash, file_path, analysis_text in new_results:
                        prepared = await prepare_local_image_async(file_path)
                        file_path.with_suffix(".txt").write_text(analysis_text, encoding="utf-8")
                        record = await uow.emojis.set(
                            file_hash,
                            file_name=file_path.name,
                            file_path=str(file_path.relative_to(self._emoji_dir)),
                            mime_type=prepared.mime_type,
                            original_width=prepared.original_width,
                            original_height=prepared.original_height,
                            analysis_text=analysis_text,
                            image_source="部署者提供",
                        )
                        records_by_hash[file_hash] = record
                        use_counts[file_hash] = record.use_count
                        existing[file_hash] = analysis_text
                    await uow.commit()
            except Exception as exc:
                self._logger.error(f"保存表情包解析结果失败: {exc}")

        self._rebuild_mapping(
            image_files,
            existing,
            path_to_hash,
            use_counts,
            records_by_hash,
        )
        with self._disk_sync_lock:
            self._last_dir_snapshot = snapshot_before
        await self._cleanup_stale_emoji_records(hash_to_path)

    async def _cleanup_stale_emoji_records(self, disk_files: dict[str, Path]) -> None:
        """删除数据库中文件已不存在的表情包记录，更新文件已重命名的记录。"""
        disk_hashes = set(disk_files.keys())
        try:
            async with self._uow_factory() as uow:
                all_records = await uow.emojis.list_all()
                for record in all_records:
                    full_path = self._emoji_dir / record.file_path
                    if full_path.exists() and full_path.is_file():
                        new_rel = str(full_path.relative_to(self._emoji_dir))
                        if new_rel != record.file_path or full_path.name != record.file_name:
                            await uow.emojis.rename(
                                record.file_hash,
                                new_file_name=full_path.name,
                                new_file_path=new_rel,
                            )
                        continue
                    if record.file_hash in disk_hashes:
                        disk_path = disk_files[record.file_hash]
                        new_rel = str(disk_path.relative_to(self._emoji_dir))
                        if new_rel != record.file_path or disk_path.name != record.file_name:
                            await uow.emojis.rename(
                                record.file_hash,
                                new_file_name=disk_path.name,
                                new_file_path=new_rel,
                            )
                        continue
                    self._logger.debug(f"清理失效表情包记录: {record.file_name} (文件不存在)")
                    await uow.emojis.delete(record.file_hash)
                await uow.commit()
        except Exception as exc:
            self._logger.error(f"表情包数据库清理失败: {exc}")

    async def _parse_batch(
        self,
        items: list[tuple[str, Path]],
    ) -> list[tuple[str, Path, str]]:
        """并发解析一批图片，返回 (hash, path, analysis_text) 列表"""
        if not items or self._vision_provider is None:
            return [(h, p, "[未配置视觉模型]") for h, p in items]

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def parse_one(file_hash: str, file_path: Path) -> tuple[str, Path, str]:
            async with semaphore:
                try:
                    prepared = await prepare_local_image_async(file_path)
                    import base64
                    b64 = base64.b64encode(prepared.image_bytes).decode("utf-8")
                    image_url = f"data:{prepared.mime_type};base64,{b64}"
                    messages: list[dict] = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": self._PARSE_PROMPT},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ]
                    response = await asyncio.wait_for(
                        self._vision_provider.chat(messages),
                        timeout=60.0,
                    )
                    content = response.get("content", "")
                    text = content.strip() if isinstance(content, str) else str(content)
                    result_text = text if text else "[解析失败]"
                    self._logger.debug(f"解析表情包 {file_path.name}: {result_text[:40]}")
                    return (file_hash, file_path, result_text)
                except Exception as exc:
                    self._logger.error(f"解析表情包失败 {file_path.name}: {exc}")
                    return (file_hash, file_path, "[解析失败]")

        tasks = [parse_one(h, p) for h, p in items]
        return list(await asyncio.gather(*tasks))

    def _list_image_files(self) -> list[Path]:
        """列出表情包目录下的所有图片文件"""
        extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        files: list[Path] = []
        try:
            for child in sorted(self._emoji_dir.iterdir()):
                if child.is_file() and child.suffix.lower() in extensions:
                    files.append(child)
        except OSError as exc:
            self._logger.error(f"扫描表情包目录失败: {exc}")
        return files
