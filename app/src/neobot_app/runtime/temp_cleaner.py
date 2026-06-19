"""TempCleaner — 沙箱临时文件自动清理。

扫描 ``data/sandbox/temp/`` 目录，删除超过指定时间未修改的文件。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from neobot_contracts.ports.logging import Logger, NullLogger


class TempCleaner:
    """沙箱临时文件清理器。

    按固定间隔扫描目录，清理过期的临时文件。
    """

    def __init__(
        self,
        temp_dir: str | Path,
        *,
        max_age_seconds: int = 1800,
        scan_interval_seconds: int = 300,
        logger: Logger | None = None,
    ) -> None:
        self._temp_dir = Path(temp_dir)
        self._max_age = max_age_seconds
        self._scan_interval = scan_interval_seconds
        self._logger = logger or NullLogger()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def temp_dir(self) -> Path:
        return self._temp_dir

    def start(self) -> None:
        """启动后台清理循环。"""
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        self._logger.info(
            f"TempCleaner 已启动: dir={self._temp_dir}, max_age={self._max_age}s, interval={self._scan_interval}s"
        )

    async def stop(self) -> None:
        """停止后台清理循环。"""
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._logger.info("TempCleaner 已停止")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._cleanup_once()
            except Exception as exc:
                self._logger.warning(f"TempCleaner 清理异常: {exc}")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._scan_interval,
                )
                break
            except TimeoutError:
                pass

    def _cleanup_once(self) -> None:
        """执行一次清理：删除过期文件。"""
        if not self._temp_dir.is_dir():
            return

        now = time.time()
        cutoff = now - self._max_age
        removed = 0

        for entry in self._temp_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    entry.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                pass

        if removed:
            self._logger.debug("TempCleaner: 清理了 %d 个过期文件", removed)
