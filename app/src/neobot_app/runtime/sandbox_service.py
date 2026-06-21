"""SandboxService — 沙箱文件操作服务。

提供路径解析、文件读/写/删/列/移/拷贝操作，所有路径需在沙箱边界内。
"""

from __future__ import annotations

import glob as glob_module
import os
import shutil
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
        """读取文件内容。"""
        resolved = path.resolve()
        if not self.is_path_allowed(resolved):
            raise PermissionError(f"路径不允许: {path}")
        if not resolved.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        return resolved.read_bytes()

    async def write_file(self, path: Path, data: bytes) -> None:
        """写入文件。父目录自动创建。"""
        resolved = path.resolve()
        if not self._is_within_sandbox(resolved):
            raise PermissionError(f"写入路径越界: {path}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(data)

    async def delete_file(self, path: Path) -> None:
        """删除文件或空目录。"""
        resolved = path.resolve()
        if not self._is_within_sandbox(resolved):
            raise PermissionError(f"删除路径越界: {path}")
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
                if fp.is_file():
                    stat = fp.stat()
                    result.append({
                        "name": fp.name,
                        "path": str(fp.relative_to(self._root)),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
        else:
            for fp in sorted(resolved.iterdir()):
                stat = fp.stat()
                result.append({
                    "name": fp.name,
                    "path": str(fp.relative_to(self._root)) if fp.is_file() else "",
                    "size": stat.st_size if fp.is_file() else 0,
                    "mtime": stat.st_mtime,
                    "is_dir": fp.is_dir(),
                })
        return result

    async def move_file(self, src: Path, dst: Path) -> None:
        """移动文件或目录。"""
        src_r = src.resolve()
        dst_r = dst.resolve()
        if not self._is_within_sandbox(src_r):
            raise PermissionError(f"源路径越界: {src}")
        if not self._is_within_sandbox(dst_r):
            raise PermissionError(f"目标路径越界: {dst}")
        dst_r.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_r), str(dst_r))

    async def copy_file(self, src: Path, dst: Path) -> None:
        """复制文件。"""
        src_r = src.resolve()
        dst_r = dst.resolve()
        if not self.is_path_allowed(src_r):
            raise PermissionError(f"源路径不允许: {src}")
        if not self._is_within_sandbox(dst_r):
            raise PermissionError(f"目标路径越界: {dst}")
        dst_r.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_r), str(dst_r))

    # ── 内部方法 ──

    def _is_within_sandbox(self, path: Path) -> bool:
        """检查路径是否在沙箱根目录下。"""
        try:
            path.relative_to(self._root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _sanitize_flow_id(chat_flow_id: str) -> str:
        """清理聊天流 ID，防止路径遍历。"""
        sanitized = chat_flow_id.replace("..", "").replace("/", "").replace("\\", "")
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
