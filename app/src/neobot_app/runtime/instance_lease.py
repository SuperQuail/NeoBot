"""用操作系统文件锁保证同一数据目录只启动一个 NeoBot。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class InstanceAlreadyRunning(RuntimeError):
    pass


class InstanceLease:
    def __init__(self, data_dir: Path) -> None:
        self.directory = Path(data_dir).resolve() / ".neobot"
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        if self._file is not None:
            return
        if self.directory.is_symlink():
            raise ValueError("实例控制目录不能是符号链接")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / "instance.lock"
        if path.is_symlink():
            raise ValueError("实例锁不能是符号链接")
        stream = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if path.stat().st_size == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise InstanceAlreadyRunning("这个数据目录已有 NeoBot 在运行，请连接现有实例") from error
        self._file = stream

    def close(self) -> None:
        stream, self._file = self._file, None
        if stream is not None:
            stream.close()

    def __enter__(self) -> InstanceLease:
        self.acquire()
        return self

    def __exit__(self, *_arguments: object) -> None:
        self.close()
