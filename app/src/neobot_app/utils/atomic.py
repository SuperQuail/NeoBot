"""原子写入小文件：同目录临时文件 + fsync + ``os.replace``。

覆盖写一个已存在的文件时，进程若在写到一半时被杀（崩溃、断电、任务管理器结束），
磁盘上会留下被截断的内容，下次启动解析 JSON/TOML 直接失败，甚至把用户的配置
或统计清零。凡是「覆盖写一个已存在的小文件」都应走这里。
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

#: Windows 上 os.replace 需要目标文件的 DELETE 权限：目标被编辑器/杀软/同步盘
#: 短暂持有句柄时会失败（WinError 5）。这类占用通常是瞬时的，短退避重试即可，
#: 而旧的就地 open(path, "w") 在这些场景下反而能成功——不重试等于新增失败面。
_REPLACE_RETRIES = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.05


def _replace_with_retry(source: str, target: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:  # WinError 5 / 目标被占用
            last_error = exc
            if attempt == _REPLACE_RETRIES - 1:
                break
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
    assert last_error is not None
    raise last_error


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """把 ``text`` 原子地写到 ``path``（先写同目录临时文件，再整体替换）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
