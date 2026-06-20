"""TempCleaner — 沙箱临时文件自动清理。

扫描 ``data/sandbox/temp/`` 目录：
- 删除超过指定时间未修改的文件
- 删除空目录
- 修复递归嵌套（temp/X/temp/X → 合并到 temp/X）
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path

from neobot_contracts.ports.logging import Logger, NullLogger


class TempCleaner:
    """沙箱临时文件清理器。

    按固定间隔扫描 temp/ 目录，清理过期临时文件、空目录和嵌套异常。
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
        """执行一次清理。"""
        if not self._temp_dir.is_dir():
            return

        now = time.time()
        cutoff = now - self._max_age
        files_removed = 0
        dirs_removed = 0
        nests_fixed = 0

        # 1. 清理过期文件
        for entry in self._temp_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    entry.unlink(missing_ok=True)
                    files_removed += 1
            except OSError:
                pass

        # 2. 修复递归嵌套: temp/Group_X/temp/Group_X → 内容提到 temp/Group_X
        for chat_dir in self._temp_dir.iterdir():
            if not chat_dir.is_dir():
                continue
            nested_temp = chat_dir / "temp"
            if not nested_temp.is_dir():
                continue
            for nested_chat in nested_temp.iterdir():
                if not nested_chat.is_dir():
                    continue
                target = self._temp_dir / nested_chat.name
                if target.exists():
                    # 目标已存在 → 只移文件不覆盖
                    for f in nested_chat.rglob("*"):
                        if f.is_file():
                            try:
                                shutil.move(str(f), str(target / f.name))
                            except OSError:
                                pass
                else:
                    try:
                        shutil.move(str(nested_chat), str(target))
                    except OSError:
                        pass
                nests_fixed += 1
            # 删除嵌套的 temp 目录
            try:
                shutil.rmtree(str(nested_temp))
                dirs_removed += 1
            except OSError:
                pass

        # 3. 清理空目录（从深到浅）
        for root, dirs, files in os_walk_topdown(str(self._temp_dir)):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        dirs_removed += 1
                except OSError:
                    pass

        if files_removed or dirs_removed or nests_fixed:
            self._logger.debug(
                f"TempCleaner: 清理 {files_removed} 过期文件, "
                f"{dirs_removed} 空目录, 修复 {nests_fixed} 嵌套"
            )


def os_walk_topdown(path: str):
    """类似 os.walk 但返回列表（避免迭代中修改目录的问题）。"""
    result = []
    for root, dirs, files in os.walk(path, topdown=True):
        result.append((root, list(dirs), list(files)))
    return result
