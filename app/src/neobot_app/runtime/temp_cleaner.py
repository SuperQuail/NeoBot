"""TempCleaner — 沙箱临时文件清理（工具类，由 AI 或 CLI 按需调用）。"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from neobot_contracts.ports.logging import Logger, NullLogger


class TempCleaner:
    """沙箱临时文件清理器。

    不自动运行，由 AI agent 通过 scan_temp_files / clean_temp_files 工具调用，
    或通过 CLI sandbox_CP 命令执行。
    """

    def __init__(
        self,
        temp_dir: str | Path,
        *,
        max_age_seconds: int = 1800,
        logger: Logger | None = None,
    ) -> None:
        self._temp_dir = Path(temp_dir)
        self._max_age = max_age_seconds
        self._logger = logger or NullLogger()

    @property
    def temp_dir(self) -> Path:
        return self._temp_dir

    def get_status(self) -> dict:
        """只读扫描临时目录，返回状态报告供 AI 决策。"""
        result = {
            "ok": True,
            "total_files": 0,
            "total_size_bytes": 0,
            "expired_files": [],
            "has_nests": False,
            "empty_dirs": 0,
        }
        if not self._temp_dir.is_dir():
            return result

        now = time.time()
        cutoff = now - self._max_age

        for entry in self._temp_dir.rglob("*"):
            if entry.is_file():
                result["total_files"] += 1
                try:
                    size = entry.stat().st_size
                    result["total_size_bytes"] += size
                    mtime = entry.stat().st_mtime
                    if mtime < cutoff:
                        result["expired_files"].append({
                            "path": str(entry.relative_to(self._temp_dir)),
                            "size_bytes": size,
                            "age_seconds": int(now - mtime),
                        })
                except OSError:
                    pass

        for chat_dir in self._temp_dir.iterdir():
            if not chat_dir.is_dir():
                continue
            nested_temp = chat_dir / "temp"
            if nested_temp.is_dir():
                result["has_nests"] = True

        # 统计空目录
        for root, dirs, _files in os_walk_topdown(str(self._temp_dir)):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    if not any(dir_path.iterdir()):
                        result["empty_dirs"] += 1
                except OSError:
                    pass

        result["expired_count"] = len(result["expired_files"])
        # 限制过期文件列表最长 50 条，避免 context 爆炸
        if len(result["expired_files"]) > 50:
            result["expired_files"] = result["expired_files"][:50]
            result["expired_truncated"] = True

        return result

    def run_once(self) -> dict:
        """执行一次清理并返回结果统计。"""
        result = self._cleanup_once()
        return result

    def _cleanup_once(self) -> dict:
        """执行一次清理并返回统计信息。"""
        result = {"files_removed": 0, "dirs_removed": 0, "nests_fixed": 0}
        if not self._temp_dir.is_dir():
            return result

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

        result["files_removed"] = files_removed
        result["dirs_removed"] = dirs_removed
        result["nests_fixed"] = nests_fixed

        if files_removed or dirs_removed or nests_fixed:
            self._logger.info(
                f"TempCleaner: 清理 {files_removed} 过期文件, "
                f"{dirs_removed} 空目录, 修复 {nests_fixed} 嵌套"
            )
        return result


def os_walk_topdown(path: str):
    """类似 os.walk 但返回列表（避免迭代中修改目录的问题）。"""
    result = []
    for root, dirs, files in os.walk(path, topdown=True):
        result.append((root, list(dirs), list(files)))
    return result
