"""原子写入小文件：同目录临时文件 + fsync + ``os.replace``。

覆盖写一个已存在的文件时，进程若在写到一半时被杀（崩溃、断电、任务管理器结束），
磁盘上会留下被截断的内容，下次启动解析 JSON/TOML 直接失败，甚至把用户的配置
或统计清零。凡是「覆盖写一个已存在的小文件」都应走这里。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


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
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
