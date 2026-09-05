"""聊天管线上下文记录器（Debug 模式）。

在 debug 模式开启时，把每次模型调用的完整上下文(messages)落盘为独立 JSON 文件，
用于事后分析 token 构成。仅保留最近 max_files(默认 100)个文件，超出自动清理最旧的。

文件命名: ctx_<YYYYmmdd_HHMMSS_ffffff>_<seq>.json
目录: <DATA_DIR>/debug/context/
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger


class ContextRecorder:
    """把完整聊天上下文写入滚动文件集(最新 N 个)。"""

    def __init__(
        self,
        log_dir: Path,
        *,
        max_files: int = 100,
        logger: Logger | None = None,
    ) -> None:
        if max_files <= 0:
            raise ValueError("max_files must be greater than 0")
        self._log_dir = log_dir
        self._max_files = max_files
        self._lock = threading.Lock()
        self._logger = logger or NullLogger()
        self._seq = 0
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._prune()
        self._logger.info(
            "ContextRecorder 已初始化",
            log_dir=str(self._log_dir),
            max_files=max_files,
        )

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def record_context(self, payload: dict[str, Any]) -> Path:
        """落盘一次模型调用上下文,返回写入的文件路径。"""
        with self._lock:
            self._seq += 1
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target = self._log_dir / f"ctx_{stamp}_{self._seq:04d}.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            self._prune()
        return target

    def _prune(self) -> None:
        """清理最旧文件,只保留最新 max_files 个。"""
        files = sorted(self._log_dir.glob("ctx_*.json"))
        overflow = len(files) - self._max_files
        if overflow <= 0:
            return
        for old in files[:overflow]:
            try:
                old.unlink()
            except OSError:
                pass
