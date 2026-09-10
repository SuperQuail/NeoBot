"""SandboxService — 沙箱文件操作服务。

提供路径解析、文件读/写/删/列/移/拷贝操作，所有路径需在沙箱边界内。
"""

from __future__ import annotations

import asyncio
import glob as glob_module
import hashlib
import os
import shutil
import tempfile
import threading
from collections import OrderedDict
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

# ── 文件类型检测：magic bytes ──

MAX_TEXT_READ_BYTES = 65536   # 文本文件单次返回上限（64KB）
MAX_BASE64_BYTES = 512        # 未知二进制 base64 预览上限（0.5KB）

_IMAGE_SIGNATURES: list[tuple[bytes, str]] = [
    (b'\x89PNG\r\n\x1a\n', 'PNG'),
    (b'\xff\xd8\xff', 'JPEG'),
    (b'GIF87a', 'GIF'),
    (b'GIF89a', 'GIF'),
    (b'BM', 'BMP'),
    (b'\x00\x00\x01\x00', 'ICO'),
]

_BINARY_SIGNATURES: list[tuple[bytes, str]] = [
    (b'%PDF', 'PDF'),
    (b'PK\x03\x04', 'ZIP/Office'),
    (b'\x7fELF', 'ELF'),
    (b'MZ', 'PE/EXE'),
    (b'\x1f\x8b', 'GZip'),
    (b'BZh', 'BZip2'),
    (b'\x1f\x9d', 'Compress'),
    (b'\x00\x00\x01\xba', 'MPEG'),
    (b'\x00\x00\x01\xb3', 'MPEG'),
    (b'fLaC', 'FLAC'),
    (b'ID3', 'MP3'),
    (b'OggS', 'OGG'),
    (b'RIFF', 'RIFF'),  # AVI/WAV/WEBP — checked further below
    (b'\x1aE\xdf\xa3', 'WebM/MKV'),
    (b'ftyp', 'MP4'),   # at offset 4
    (b'\xd0\xcf\x11\xe0', 'MS Office (OLE)'),
]


def detect_file_type(path: Path) -> dict[str, Any]:
    """检测文件类型（仅读头部字节，不加载完整文件）。

    返回 ``{"type": "image"|"binary"|"text"|"unknown", "size": int, "format": str|None}``.
    """
    try:
        stat = path.stat()
        size = stat.st_size
    except OSError:
        return {"type": "error", "size": 0, "format": None}

    if not path.is_file():
        return {"type": "error", "size": size, "format": None}

    try:
        with open(path, 'rb') as f:
            header = f.read(16)
    except OSError:
        return {"type": "error", "size": size, "format": None}

    if len(header) == 0:
        return {"type": "empty", "size": 0, "format": None}

    # 图像签名
    for magic, fmt in _IMAGE_SIGNATURES:
        if header.startswith(magic):
            return {"type": "image", "size": size, "format": fmt}

    # WEBP: RIFF????WEBP
    if header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'WEBP':
        return {"type": "image", "size": size, "format": "WEBP"}

    # 已知二进制签名
    for magic, fmt in _BINARY_SIGNATURES:
        if header.startswith(magic):
            # MP4: ftyp at offset 4
            if magic == b'ftyp':
                continue
            # RIFF that isn't WEBP → treat as generic binary
            if magic == b'RIFF':
                return {"type": "binary", "size": size, "format": "RIFF container (AVI/WAV)"}
            return {"type": "binary", "size": size, "format": fmt}

    if header[4:8] == b'ftyp':
        return {"type": "binary", "size": size, "format": "MP4"}

    # 尝试 UTF-8 解码前 16 字节区分文本/未知二进制
    try:
        header.decode('utf-8')
        return {"type": "text", "size": size, "format": None}
    except UnicodeDecodeError:
        return {"type": "unknown", "size": size, "format": None}


class SandboxService:
    """沙箱文件操作服务。

    职责：
      - 路径合法性验证（防 path traversal）
      - 文件读写/删除/列表/移动/复制
      - 临时目录管理（按 chat_flow_id 隔离）
      - 只读目录注册（emoji/, gallery/）
    """

    def __init__(
        self,
        sandbox_root: Path,
        lock: Any = None,
        allowed_read_dirs: list[Path] | None = None,
        max_total_size_bytes: int = 2 * 1024 * 1024 * 1024,
    ) -> None:
        self._root = sandbox_root.resolve()
        self._lock = lock
        self._max_total_size = max_total_size_bytes
        self._file_locks_guard = threading.Lock()
        self._file_locks: dict[str, tuple[Any, int]] = {}
        # Shared by all AgentFileTools facades using this service.
        self._file_observations: OrderedDict = OrderedDict()
        self._observations_guard = threading.Lock()
        self._allowed_read_dirs: list[Path] = []
        if allowed_read_dirs:
            for d in allowed_read_dirs:
                resolved = Path(d).resolve()
                self._allowed_read_dirs.append(resolved)

    # ── 路径解析 ──

    def resolve_path(
        self,
        relative_path: str,
        chat_flow_id: str | None = None,
    ) -> Path:
        """将相对路径解析为沙箱内的绝对路径。

        如果提供 chat_flow_id，路径基准为 ``sandbox/temp/{chat_flow_id}/``。
        否则基准为沙箱根目录。
        """
        base = self._root
        if chat_flow_id:
            base = self._root / "temp" / self._sanitize_flow_id(chat_flow_id)
        # 拼接并规范化
        candidate = (base / relative_path).resolve()
        # 验证在沙箱边界内
        if not self._is_within_sandbox(candidate):
            raise PermissionError(f"路径越界: {relative_path}")
        return candidate

    SHARED_DIRECTORIES = frozenset({"tools", "docs", "assets", "gift", "emoji", "gallery"})

    def resolve_agent_path(self, value: str, *, owner: str, chat_flow_id: str,
                           write: bool = False) -> Path:
        """Trusted context only. Same-flow files are shared, observations are not.

        Persistent resources require explicit shared:<allowlisted-directory>/...
        Absolute paths are accepted only within the current flow (delivery reuse).
        Symlinks/junctions are rejected, including links to another allowed root.
        """
        if not isinstance(owner, str) or not owner.strip():
            raise PermissionError("trusted owner required")
        if not isinstance(chat_flow_id, str) or not chat_flow_id.strip():
            raise PermissionError("trusted chat_flow_id required")
        if len(owner) > 512 or len(chat_flow_id) > 256:
            raise ValueError("context too long")
        # Existing temp paths sanitize ':' to '_'. Reject alias spellings rather
        # than letting a different trusted flow identity enter that same folder.
        if ":" in chat_flow_id:
            kind, identifier = chat_flow_id.split(":", 1)
            if kind not in {"group", "private"} or not identifier.isascii() or not identifier.isdecimal():
                raise PermissionError("use canonical group:<digits>/private:<digits> flow identity")
        else:
            kind, _, identifier = chat_flow_id.partition("_")
            if (chat_flow_id != self._sanitize_flow_id(chat_flow_id)
                    or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_." for ch in chat_flow_id)
                    or (kind in {"group", "private"} and identifier.isdecimal())):
                raise PermissionError("noncanonical or aliased flow identity")
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError("invalid path")
        value = value.replace("\\", "/")
        if value.startswith("shared:"):
            relative = value[7:]
            parts = relative.split("/")
            if parts[0] not in self.SHARED_DIRECTORIES:
                raise PermissionError("shared directory is not allowlisted")
            base = self._root / parts[0]
            # Explicitly registered external resources remain read-only.
            external = [p for p in self._allowed_read_dirs if p.name == parts[0]]
            if external:
                if write:
                    raise PermissionError("shared resource is read-only")
                base = external[0]
            value = "/".join(parts[1:]) or "."
        else:
            base = self.get_temp_dir(chat_flow_id)
        if ".." in value.split("/"):
            raise PermissionError("parent traversal is not allowed")
        # Reject Windows alternate streams, drive-relative paths, and device names.
        raw = Path(value)
        if not raw.is_absolute() and (raw.drive or ":" in value):
            raise PermissionError("invalid relative path")
        candidate = base / raw
        for component in candidate.parts[1:]:
            if ":" in component or (hasattr(os.path, "isreserved") and os.path.isreserved(component)):
                raise PermissionError("reserved path component/alternate data stream")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(base.absolute()):
            raise PermissionError("path is outside current flow/shared directory")
        for part in (candidate, *candidate.parents):
            if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                raise PermissionError("symlink/junction paths are not allowed")
        if write and not self._is_within_sandbox(resolved):
            raise PermissionError("write outside sandbox")
        if not self.is_path_allowed(resolved):
            raise PermissionError("path is not allowed")
        return resolved

    def resolve_read_path(
        self,
        relative_path: str,
        chat_flow_id: str | None = None,
    ) -> Path:
        """与 resolve_path 相同，但也允许只读目录（emoji/, gallery/ 等）。"""
        try:
            return self.resolve_path(relative_path, chat_flow_id)
        except PermissionError:
            for ad in self._allowed_read_dirs:
                candidate = (ad / relative_path).resolve()
                try:
                    candidate.relative_to(ad)
                except ValueError:
                    continue
                if candidate.is_file() or candidate.is_dir():
                    return candidate
            raise

    def is_path_allowed(self, path: Path) -> bool:
        """检查路径是否在沙箱或 allowed_read_dirs 内。"""
        resolved = path.resolve()
        if self._is_within_sandbox(resolved):
            return True
        for ad in self._allowed_read_dirs:
            try:
                resolved.relative_to(ad)
                return True
            except ValueError:
                continue
        return False

    # ── 临时目录 ──

    def get_temp_dir(self, chat_flow_id: str) -> Path:
        """返回指定聊天流的临时目录路径（不创建）。"""
        return self._root / "temp" / self._sanitize_flow_id(chat_flow_id)

    def ensure_temp_dir(self, chat_flow_id: str) -> Path:
        """创建并返回指定聊天流的临时目录。"""
        d = self.get_temp_dir(chat_flow_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── 文件操作 ──

    async def read_file(self, path: Path) -> bytes:
        """读取文件内容。

        文本文件超过 MAX_TEXT_READ_BYTES 时仅返回前 MAX_TEXT_READ_BYTES 字节；
        二进制/未知类型文件保持完整读取（不对二进制做截断）。

        文件 IO 交给工作线程：这些方法原先声明为 async 但内部零 await，
        同步磁盘操作实际是跑在事件循环上的（大文件/慢盘会卡住整个 Bot）。
        """
        return await asyncio.to_thread(self._read_file_sync, path)

    def _read_file_sync(self, path: Path) -> bytes:
        resolved = path.resolve()
        if not self.is_path_allowed(resolved):
            raise PermissionError(f"路径不允许: {path}")
        if not resolved.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        data = resolved.read_bytes()
        if len(data) > MAX_TEXT_READ_BYTES and detect_file_type(resolved)["type"] == "text":
            data = data[:MAX_TEXT_READ_BYTES]
        return data

    @contextmanager
    def file_lock(self, path: Path):
        """Per-canonical-file, cross-thread lock; idle entries are reclaimed."""
        key = os.path.normcase(str(path.resolve()))
        with self._file_locks_guard:
            lock, users = self._file_locks.get(key, (threading.RLock(), 0))
            self._file_locks[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._file_locks_guard:
                _, users = self._file_locks[key]
                if users == 1:
                    del self._file_locks[key]
                else:
                    self._file_locks[key] = (lock, users - 1)

    def read_complete(self, path: Path, max_bytes: int = 16 * 1024 * 1024) -> bytes:
        """Complete bounded read for editing, NEVER a display preview.

        The old read_file byte-preview contract remains for existing consumers.
        Too-large input fails rather than returning data safe-looking to overwrite.
        """
        if not self.is_path_allowed(path):
            raise PermissionError(f"路径不允许: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        with path.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"file_too_large: limit {max_bytes} bytes")
        return data

    @staticmethod
    def file_version(path: Path, data: bytes) -> str:
        stat = path.stat()
        metadata = f"{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_ino}:".encode()
        return hashlib.sha256(metadata + data).hexdigest()

    def atomic_write(self, path: Path, data: bytes) -> None:
        """Caller holds file_lock; fsync then replace on the same filesystem."""
        resolved = path.resolve()
        if not self._is_within_sandbox(resolved):
            raise PermissionError(f"写入路径越界: {path}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".neobot-write-", dir=resolved.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if resolved.exists():
                os.chmod(temporary, resolved.stat().st_mode)
            os.replace(temporary, resolved)
        finally:
            if os.path.exists(temporary):
                os.chmod(temporary, 0o600)
                os.unlink(temporary)

    async def write_file(self, path: Path, data: bytes) -> None:
        """Trusted service API, atomic but deliberately not observation-gated.

        Agent callers must use AgentFileTools (or the legacy skill adapter).
        """
        await asyncio.to_thread(self._write_file_sync, path, data)

    def _write_file_sync(self, path: Path, data: bytes) -> None:
        with self.file_lock(path):
            self.atomic_write(path, data)

    async def delete_file(self, path: Path) -> None:
        """删除文件或空目录。"""
        await asyncio.to_thread(self._delete_file_sync, path)

    def _delete_file_sync(self, path: Path) -> None:
        resolved = path.resolve()
        if not self._is_within_sandbox(resolved):
            raise PermissionError(f"删除路径越界: {path}")
        with self.file_lock(resolved):
            if resolved.is_dir():
                shutil.rmtree(resolved)
            elif resolved.is_file():
                resolved.unlink()
            else:
                raise FileNotFoundError(f"路径不存在: {path}")

    async def list_files(
        self,
        path: Path,
        pattern: str | None = None,
    ) -> list[dict]:
        """列出目录下的文件。"""
        return await asyncio.to_thread(self._list_files_sync, path, pattern)

    def _list_files_sync(self, path: Path, pattern: str | None = None) -> list[dict]:
        resolved = path.resolve()
        if not self.is_path_allowed(resolved):
            raise PermissionError(f"路径不允许: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"不是目录: {path}")

        result: list[dict] = []
        if pattern:
            search_path = str(resolved / pattern)
            for p in glob_module.iglob(search_path, recursive=True):
                fp = Path(p)
                if not fp.is_file():
                    continue
                if not self.is_path_allowed(fp):
                    continue
                stat = fp.stat()
                result.append({
                    "name": fp.name,
                    "path": self._display_path(fp),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        else:
            for fp in sorted(resolved.iterdir()):
                stat = fp.stat()
                result.append({
                    "name": fp.name,
                    "path": self._display_path(fp) if fp.is_file() else "",
                    "size": stat.st_size if fp.is_file() else 0,
                    "mtime": stat.st_mtime,
                    "is_dir": fp.is_dir(),
                })
        return result

    def _display_path(self, path: Path) -> str:
        """返回相对于沙箱根（或只读目录）的展示路径。"""
        try:
            return str(path.relative_to(self._root))
        except ValueError:
            for ad in self._allowed_read_dirs:
                try:
                    return str(path.relative_to(ad))
                except ValueError:
                    continue
        return str(path)

    async def move_file(self, src: Path, dst: Path) -> None:
        """移动文件或目录。"""
        await asyncio.to_thread(self._move_file_sync, src, dst)

    def _move_file_sync(self, src: Path, dst: Path) -> None:
        src_r = src.resolve()
        dst_r = dst.resolve()
        if not self._is_within_sandbox(src_r):
            raise PermissionError(f"源路径越界: {src}")
        if not self._is_within_sandbox(dst_r):
            raise PermissionError(f"目标路径越界: {dst}")
        with ExitStack() as locks:
            for path in sorted({src_r, dst_r}, key=lambda p: os.path.normcase(str(p))):
                locks.enter_context(self.file_lock(path))
            dst_r.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_r), str(dst_r))

    async def copy_file(self, src: Path, dst: Path) -> None:
        """复制文件。"""
        await asyncio.to_thread(self._copy_file_sync, src, dst)

    def _copy_file_sync(self, src: Path, dst: Path) -> None:
        src_r = src.resolve()
        dst_r = dst.resolve()
        if not self.is_path_allowed(src_r):
            raise PermissionError(f"源路径不允许: {src}")
        if not self._is_within_sandbox(dst_r):
            raise PermissionError(f"目标路径越界: {dst}")
        if dst_r.is_dir():
            dst_r = (dst_r / src_r.name).resolve()
            if not self._is_within_sandbox(dst_r):
                raise PermissionError(f"目标路径越界: {dst}")
        with ExitStack() as locks:
            for path in sorted({src_r, dst_r}, key=lambda p: os.path.normcase(str(p))):
                locks.enter_context(self.file_lock(path))
            if src_r == dst_r or (dst_r.exists() and os.path.samefile(src_r, dst_r)):
                raise shutil.SameFileError(str(src_r))
            dst_r.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".neobot-write-", dir=dst_r.parent)
            os.close(fd)
            try:
                shutil.copyfile(src_r, temporary)
                # Windows fsync requires a writable descriptor; apply source
                # metadata only afterwards (it may include a read-only mode).
                with open(temporary, "rb+") as stream:
                    os.fsync(stream.fileno())
                shutil.copystat(src_r, temporary)
                os.replace(temporary, dst_r)
            finally:
                if os.path.exists(temporary):
                    os.chmod(temporary, 0o600)
                    os.unlink(temporary)

    # ── 内部方法 ──

    def _is_within_sandbox(self, path: Path) -> bool:
        """检查路径是否在沙箱根目录下。"""
        try:
            path.relative_to(self._root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _sanitize_flow_id(chat_flow_id: str | None) -> str:
        """清理聊天流 ID，防止路径遍历与 Windows 非法字符。

        聊天流 ID 常见格式为 ``group:12345`` 或裸 ID；Windows 下 ``:`` 等字符
        不能出现在目录名中，否则 mkdir 抛 WinError 267。
        """
        if not chat_flow_id:
            return "unknown"
        sanitized = chat_flow_id.replace("..", "").replace("/", "").replace("\\", "")
        # Windows 路径非法字符 (<>:"|?*) 与控制字符 → 下划线
        sanitized = "".join(
            "_" if ch in '<>:"|?*' or ord(ch) < 32 else ch
            for ch in sanitized
        )
        sanitized = sanitized.strip(" .")
        return sanitized or "unknown"

    # ── 容量管理 ──

    def get_total_size(self) -> int:
        """计算沙箱内所有文件的总大小（字节）。"""
        total = 0
        for entry in self._root.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
        return total

    def check_capacity(self, additional_bytes: int = 0) -> int | None:
        """检查沙箱容量。

        返回 None 表示容量充足；返回剩余可写入字节数（≤0 时表示不足）。
        """
        current = self.get_total_size()
        remaining = self._max_total_size - current - additional_bytes
        return remaining

    @property
    def max_total_size(self) -> int:
        return self._max_total_size
