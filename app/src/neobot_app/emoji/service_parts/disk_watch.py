"""表情包目录外改的即时感知与合并刷新（由 service.py 拆分）。"""

from __future__ import annotations

import asyncio

from neobot_app.emoji.service_parts.models import EmojiEntry, _file_hash_sync, _read_sidecar_text


class _DiskWatchMixin:
    async def _refresh_loop(self) -> None:
        """后台定时刷新循环"""
        while True:
            try:
                await asyncio.sleep(self._REFRESH_INTERVAL_SECONDS)
                await self._scan_safe()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(f"表情包定时刷新失败: {exc}")

    async def _scan_safe(self) -> None:
        """带互斥的扫描(定时刷新与即时刷新不并发执行,避免重复解析/重复清理)。"""
        async with self._scan_lock:
            await self._scan_folder()

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
            # 只需要 file_hash（prepare_local_image 定义它就是原始字节的 sha256），
            # 直接算哈希即可：避免在同步路径上做 PIL 解码+缩放。本函数由
            # _notify_disk_changed 从同步访问器调用，不能 await。
            file_hash = _file_hash_sync(path)
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
