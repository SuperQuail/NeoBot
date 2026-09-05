"""EmojiService — 表情包扫描、解析、编号与提示词生成"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_contracts.models.memory import EmojiRecord
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.message.image_pipeline import prepare_local_image

if TYPE_CHECKING:
    from neobot_chat.providers.base import Provider
    from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class EmojiEntry:
    """内存中的表情包条目"""
    file_name: str
    file_path: Path
    analysis_text: str
    file_hash: str = ""
    use_count: int = 0
    image_source: str | None = None
    created_at: Any = None
    updated_at: Any = None


@dataclass(frozen=True, slots=True)
class EmojiImportResult:
    number: int
    entry: EmojiEntry


class EmojiService:
    """管理表情包的扫描、解析、编号与提示词生成"""

    _PARSE_PROMPT = (
        "请用中文描述这张表情包图片的内容，包括画面中的文字、人物、动作、情绪等。"
        "尽可能简洁，最多50个字。"
    )
    _EMOJI_DIR_NAME = "emoji"
    _REFRESH_INTERVAL_SECONDS = 300

    def __init__(
        self,
        *,
        data_dir: Path,
        uow_factory: UnitOfWorkFactory,
        vision_provider: Provider | None = None,
        max_concurrency: int = 20,
        page_size: int = 50,
        logger: Logger | None = None,
        adapter: Any = None,
        file_server: Any = None,
    ) -> None:
        self._emoji_dir = data_dir / self._EMOJI_DIR_NAME
        self._uow_factory = uow_factory
        self._vision_provider = vision_provider
        self._max_concurrency = max_concurrency
        self._page_size = page_size
        self._logger = logger or NullLogger()
        self._entries: dict[int, EmojiEntry] = {}
        self._next_number: int = 1
        self._refresh_task: asyncio.Task[None] | None = None
        self._adapter = adapter
        self._file_server = file_server
        # 外部直接修改 emoji 目录(手动放置/文件操作 agent 写入)的即时感知:
        # 读取入口检测目录快照变化 → 同步快速合并新文件 + 后台全量刷新
        self._last_dir_snapshot: tuple[tuple[str, ...], int] | None = None
        self._disk_sync_lock = threading.Lock()
        self._disk_refresh_task: asyncio.Task[None] | None = None
        self._scan_lock = asyncio.Lock()

    def bind_send_dependencies(self, adapter: Any, file_server: Any) -> None:
        """注入发送能力（适配器与文件服务器），供 send_sticker 使用。"""
        self._adapter = adapter
        self._file_server = file_server

    @property
    def emoji_count(self) -> int:
        self._notify_disk_changed()
        return len(self._entries)

    @property
    def page_size(self) -> int:
        return self._page_size

    def get_entry(self, number: int) -> EmojiEntry | None:
        self._notify_disk_changed()
        return self._entries.get(number)

    def list_entries(self) -> list[tuple[int, EmojiEntry]]:
        """返回所有表情包，按使用次数从少到多排列。"""
        self._notify_disk_changed()
        sorted_entries = sorted(self._entries.items(), key=lambda item: item[1].use_count)
        return sorted_entries

    def list_entries_paginated(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[tuple[int, EmojiEntry]], int, bool]:
        """分页返回表情包列表，按使用次数从少到多排列。

        Returns (items, total, has_more)
        """
        self._notify_disk_changed()
        limit = limit if limit is not None else self._page_size
        sorted_entries = sorted(self._entries.items(), key=lambda item: item[1].use_count)
        total = len(sorted_entries)
        page = sorted_entries[offset : offset + limit]
        has_more = offset + limit < total
        return page, total, has_more

    def search_entries(self, keyword: str, limit: int | None = None) -> list[tuple[int, EmojiEntry]]:
        """搜索表情包描述和文件名，按使用次数从少到多排列。"""
        self._notify_disk_changed()
        limit = limit if limit is not None else self._page_size
        kw = keyword.lower()
        matches: list[tuple[int, EmojiEntry]] = []
        for number, entry in self._entries.items():
            if kw in entry.analysis_text.lower() or kw in entry.file_name.lower():
                matches.append((number, entry))
        matches.sort(key=lambda item: item[1].use_count)
        return matches[:limit]

    def build_prompt_text(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> str:
        """构建表情包提示词文本，按使用次数从少到多排列（使用次数均衡器）。

        格式为 [编号]: [表情包：描述 | 已用N次]
        """
        self._notify_disk_changed()
        if not self._entries:
            return ""
        limit = limit if limit is not None else self._page_size
        sorted_entries = sorted(self._entries.items(), key=lambda item: item[1].use_count)
        page = sorted_entries[offset : offset + limit]

        lines: list[str] = []
        for number, entry in page:
            usage_info = f" | 已用{entry.use_count}次" if entry.use_count > 0 else ""
            lines.append(f"[{number}]: [表情包：{entry.analysis_text}{usage_info}]")

        total = len(sorted_entries)
        header = f"共{total}个表情包"
        if total > limit:
            header += f"，当前显示第{offset + 1}-{min(offset + limit, total)}个"
            if offset > 0:
                header += f"，往前翻页: emoji_list(offset={max(0, offset - limit)})"
            if offset + limit < total:
                header += f"，往后翻页: emoji_list(offset={offset + limit})"
        return header + "\n" + "\n".join(lines)

    async def send_sticker(
        self,
        number: int,
        *,
        text: str = "",
        group_id: Any = None,
        user_id: Any = None,
    ) -> Any:
        """发送指定编号的表情包到群聊或私聊，成功后记录使用次数。

        group_id 与 user_id 至少提供一个；两者都有时优先群聊。
        """
        if self._adapter is None or self._file_server is None:
            raise RuntimeError("表情包发送能力未注入（缺少 adapter/file_server）")
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists():
            raise FileNotFoundError(f"表情包文件不存在: {entry.file_path}")

        group_id = str(group_id or "").strip()
        user_id = str(user_id or "").strip()
        if not group_id and not user_id:
            raise ValueError("缺少 group_id 或 user_id")

        from neobot_app.utils.media_sender import prepare_image_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segments: list[dict] = []
        if text:
            segments.append({"type": "text", "data": {"text": text}})
        segments.append(prepare_image_segment(self._file_server, entry.file_path))

        resp = await self._adapter.send(conv_ref, segments)
        await self.record_usage(number)
        return resp

    async def record_usage(self, number: int) -> None:
        """记录一次表情包使用，递增 use_count。"""
        entry = self._entries.get(number)
        if entry is None:
            return
        try:
            file_hash = prepare_local_image(entry.file_path).file_hash
            async with self._uow_factory() as uow:
                await uow.emojis.increment_usage(file_hash)
                await uow.commit()
        except Exception as exc:
            self._logger.warning(f"记录表情包使用次数失败 #{number}: {exc}")
            return

        # 更新内存中的计数
        self._entries[number] = EmojiEntry(
            file_name=entry.file_name,
            file_path=entry.file_path,
            analysis_text=entry.analysis_text,
            use_count=entry.use_count + 1,
            file_hash=entry.file_hash,
            image_source=entry.image_source,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    async def start(self) -> None:
        """启动时扫描表情包文件夹"""
        self._emoji_dir.mkdir(parents=True, exist_ok=True)
        await self._scan_folder()
        with self._disk_sync_lock:
            self._last_dir_snapshot = self._dir_snapshot()
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
        if self._disk_refresh_task is not None:
            task = self._disk_refresh_task
            if not task.done():
                # 优先等待即时刷新完成(DB 操作正常收尾),避免取消进行中的
                # aiosqlite 查询导致 worker 线程在事件循环关闭后回调报错
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            self._disk_refresh_task = None
        # 停止后置空快照:迟到读取只记录基线,不再触发新的后台刷新
        with self._disk_sync_lock:
            self._last_dir_snapshot = None

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
                raise ValueError(
                    f"该图片与已有表情包重复（哈希 {file_hash[:12]}…），"
                    f"已有文件: {existing.file_name}，不允许重复加入"
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
            prepared = prepare_local_image(target_path)
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
            file_hash = prepare_local_image(entry.file_path).file_hash
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
        prepared = prepare_local_image(entry.file_path)
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
        )

    async def update_emoji_source(self, number: int, image_source: str) -> EmojiRecord | None:
        """更新表情包的图片来源。"""
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists():
            raise LookupError(f"表情包文件不存在: {entry.file_path}")

        prepared = prepare_local_image(entry.file_path)
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

        prepared = prepare_local_image(new_path)
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
        )
        self._entries[number] = updated
        return updated

    async def _scan_folder(self) -> None:
        """扫描表情包文件夹，并同步 txt、数据库与视觉解析结果。"""
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
                self._last_dir_snapshot = self._dir_snapshot()
            await self._cleanup_stale_emoji_records({})
            return

        hash_to_path: dict[str, Path] = {}
        path_to_hash: dict[Path, str] = {}
        for file_path in image_files:
            try:
                prepared = prepare_local_image(file_path)
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

                prepared = prepare_local_image(file_path)
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
                        prepared = prepare_local_image(file_path)
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
            self._last_dir_snapshot = self._dir_snapshot()
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
                    prepared = prepare_local_image(file_path)
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

    def _rebuild_mapping(
        self,
        image_files: list[Path],
        analysis_map: dict[str, str],
        path_to_hash: dict[Path, str],
        use_counts: dict[str, int] | None = None,
        records_by_hash: dict[str, EmojiRecord] | None = None,
    ) -> None:
        """根据当前文件列表和分析结果重建编号映射"""
        counts = use_counts or {}
        records = records_by_hash or {}
        # 保留仍存在的旧条目编号
        old_by_name: dict[str, tuple[int, EmojiEntry]] = {}
        for number, entry in self._entries.items():
            old_by_name[entry.file_name] = (number, entry)

        new_entries: dict[int, EmojiEntry] = {}
        # 从已有条目的真实编号集合计算，新编号必须避开已占用编号且不复用已删除编号
        used_numbers = set(self._entries.keys())
        max_existing_number = max(used_numbers, default=0)

        for file_path in image_files:
            name = file_path.name
            file_hash = path_to_hash.get(file_path)
            entry_use_count = counts.get(file_hash, 0) if file_hash else 0

            if name in old_by_name and old_by_name[name][1].file_path == file_path:
                num = old_by_name[name][0]
                analysis_text = (
                    analysis_map.get(file_hash, old_by_name[name][1].analysis_text)
                    if file_hash is not None
                    else old_by_name[name][1].analysis_text
                )
                old_entry = self._entries.get(num)
                record = records.get(file_hash) if file_hash is not None else None
                new_entries[num] = EmojiEntry(
                    file_name=name,
                    file_path=file_path,
                    analysis_text=analysis_text,
                    use_count=entry_use_count,
                    file_hash=file_hash or getattr(old_entry, "file_hash", ""),
                    image_source=(
                        record.image_source
                        if record is not None
                        else getattr(old_entry, "image_source", None)
                    ),
                    created_at=(
                        record.created_at
                        if record is not None
                        else getattr(old_entry, "created_at", None)
                    ),
                    updated_at=(
                        record.updated_at
                        if record is not None
                        else getattr(old_entry, "updated_at", None)
                    ),
                )
                if num > max_existing_number:
                    max_existing_number = num
            else:
                analysis_text = "[待解析]"
                if file_hash is not None:
                    analysis_text = analysis_map.get(file_hash, "[待解析]")
                old_entry = None
                if name in old_by_name:
                    num = old_by_name[name][0]
                    old_entry = self._entries.get(num)
                else:
                    max_existing_number += 1
                    num = max_existing_number
                record = records.get(file_hash) if file_hash is not None else None
                new_entries[num] = EmojiEntry(
                    file_name=name,
                    file_path=file_path,
                    analysis_text=analysis_text,
                    use_count=entry_use_count,
                    file_hash=file_hash or getattr(old_entry, "file_hash", ""),
                    image_source=(
                        record.image_source
                        if record is not None
                        else getattr(old_entry, "image_source", None)
                    ),
                    created_at=(
                        record.created_at
                        if record is not None
                        else getattr(old_entry, "created_at", None)
                    ),
                    updated_at=(
                        record.updated_at
                        if record is not None
                        else getattr(old_entry, "updated_at", None)
                    ),
                )

        removed = set(self._entries) - set(new_entries)
        if removed:
            self._logger.info(f"表情包文件已删除，移除编号: {sorted(removed)}")

        self._entries = new_entries
        self._next_number = max(new_entries) + 1 if new_entries else 1

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

    async def _refresh_loop(self) -> None:
        """后台定时刷新循环"""
        while True:
            try:
                await asyncio.sleep(self._REFRESH_INTERVAL_SECONDS)
                self._logger.debug("开始定时刷新表情包")
                await self._scan_safe()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(f"表情包定时刷新失败: {exc}")

    async def _scan_safe(self) -> None:
        """带互斥的扫描(定时刷新与即时刷新不并发执行,避免重复解析/重复清理)。"""
        async with self._scan_lock:
            await self._scan_folder()

    # ── 外部目录变化的即时感知(手动放文件/文件操作 agent 写入等) ──

    def _dir_snapshot(self) -> tuple[tuple[str, ...], int]:
        """当前目录快照:文件名列表 + 目录 mtime(廉价,每次读取调用)。"""
        try:
            files = tuple(
                sorted(p.name for p in self._emoji_dir.iterdir() if p.is_file())
            )
        except OSError:
            files = ()
        try:
            mtime = self._emoji_dir.stat().st_mtime_ns
        except OSError:
            mtime = -1
        return files, mtime

    def _notify_disk_changed(self) -> None:
        """读取入口调用:检测 emoji 目录是否被外部直接修改。

        背景:add_image_bytes/delete_entry 等写操作内部都会刷新索引,
        但手动放置文件、文件操作 agent 直接写入目录等路径不经过本服务,
        此前只能等待 300 秒定时刷新,导致 agent 添加表情包后看不到新列表。
        这里在读取时检测目录变化,变化则:
        1. 同步把新文件合并进索引(立即可见,不等视觉解析/数据库);
        2. 安排后台全量刷新修正 use_count/描述/清理。
        """
        snapshot = self._dir_snapshot()
        with self._disk_sync_lock:
            if self._last_dir_snapshot is None:
                # 服务未 start()(未完成初始扫描):只记录基线,不触发刷新,
                # 避免在未初始化场景下启动后台数据库任务
                self._last_dir_snapshot = snapshot
                return
            if snapshot == self._last_dir_snapshot:
                return
            self._last_dir_snapshot = snapshot
            self._merge_disk_entries_fast()
        self._schedule_disk_refresh()

    def _merge_disk_entries_fast(self) -> None:
        """同步快速合并:磁盘新文件立即进入索引。

        描述取 txt 侧文件,否则标 [待解析];use_count 用旧条目值或 0;
        精确数据由后台 _scan_folder 修正(编号经 _rebuild_mapping 保留)。
        """
        known = {entry.file_path for entry in self._entries.values()}
        for path in self._list_image_files():
            if path in known:
                continue
            text = _read_sidecar_text(path) or "[待解析]"
            try:
                prepared = prepare_local_image(path)
                file_hash = prepared.file_hash
            except Exception:
                file_hash = ""
            number = self._next_number
            self._next_number += 1
            self._entries[number] = EmojiEntry(
                file_name=path.name,
                file_path=path,
                analysis_text=text,
                file_hash=file_hash,
                use_count=0,
                image_source=None,
            )
            self._logger.info(
                f"检测到表情包目录新增文件,已即时加入列表: {path.name} (#{number})"
            )

    def _schedule_disk_refresh(self) -> None:
        """安排一次后台全量刷新(不等待视觉解析,避免阻塞读取)。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._disk_refresh_task is None or self._disk_refresh_task.done():
            self._disk_refresh_task = loop.create_task(self._disk_refresh_guard())

    async def _disk_refresh_guard(self) -> None:
        try:
            await self._scan_safe()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.error(f"表情包即时刷新失败: {exc}")


def _detect_image_suffix(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "gif"
    return "png"


def _read_sidecar_text(file_path: Path) -> str | None:
    txt_path = file_path.with_suffix(".txt")
    if not txt_path.exists():
        return None
    try:
        text = txt_path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def _safe_emoji_file_name(file_name: str | None, suffix: str) -> str:
    suffix = suffix.lstrip(".").lower() or "png"
    raw_name = Path(str(file_name or "")).name.strip()
    if not raw_name:
        from uuid import uuid4
        return f"emoji_{uuid4().hex[:12]}.{suffix}"
    stem = Path(raw_name).stem.strip() or f"emoji_{uuid4().hex[:12]}"
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return f"{cleaned[:80] or 'emoji'}.{suffix}"
