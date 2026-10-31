"""EmojiService 构造、依赖注入与生命周期（由 service.py 拆分）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncio
import threading

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.emoji.service_parts.models import EmojiEntry

if TYPE_CHECKING:
    from neobot_chat.providers.base import Provider
    from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


class _CoreMixin:
    _PARSE_PROMPT = (
        "请用中文描述这张表情包图片的内容，包括画面中的文字、人物、动作、情绪等。"
        "尽可能简洁，最多50个字。"
    )
    _EMOJI_DIR_NAME = "emoji"
    _REFRESH_INTERVAL_SECONDS = 300
    #: 候选曝光分：被选进候选池但未发送时的一次记数
    _CANDIDATE_EXPOSURE = 0.5

    def __init__(
        self,
        *,
        data_dir: Path,
        uow_factory: UnitOfWorkFactory,
        vision_provider: Provider | None = None,
        max_concurrency: int = 20,
        page_size: int = 50,
        favorite_limit: int = 10,
        logger: Logger | None = None,
        adapter: Any = None,
        file_server: Any = None,
    ) -> None:
        self._emoji_dir = data_dir / self._EMOJI_DIR_NAME
        self._uow_factory = uow_factory
        self._vision_provider = vision_provider
        self._max_concurrency = max_concurrency
        self._page_size = page_size
        self._favorite_limit = max(int(favorite_limit), 0)
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
        self._empty_scan_reported = False

    def install_vision_provider(self, provider: Provider | None) -> Provider | None:
        """换用新的视觉 provider，返回旧的（热重载：只换引用，不负责关闭旧对象）。

        issue #75：表情包的图片解析走 `self._vision_provider`（见 `_describe_*`），
        而它在构造期就固化了 —— 换了视觉模型不推给它，表情包识别会一直用旧模型。
        """
        previous = self._vision_provider
        self._vision_provider = provider
        return previous

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

    @property
    def favorite_limit(self) -> int:
        return self._favorite_limit

    def get_entry(self, number: int) -> EmojiEntry | None:
        self._notify_disk_changed()
        return self._entries.get(number)

    def find_number_by_hash(self, file_hash: str) -> int | None:
        """按内容哈希反查表情包编号（重复加入时用它做幂等返回）。"""
        self._notify_disk_changed()
        for number, entry in self._entries.items():
            if entry.file_hash == file_hash:
                return number
        return None

    async def start(self) -> None:
        """启动时扫描表情包文件夹"""
        self._emoji_dir.mkdir(parents=True, exist_ok=True)
        # _scan_folder 自己会在「扫描前快照」上盖章；这里不能再取一次最新快照，
        # 否则启动扫描期间新写入的表情包会被误标为已处理。
        await self._scan_safe()
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
