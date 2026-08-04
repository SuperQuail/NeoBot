"""图片暂存池 —— 按会话隔离的内存图片缓存，带 TTL 过期机制。"""

from __future__ import annotations

import mimetypes
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StagedImage:
    """单条已暂存的图片记录。"""

    key: str
    file_path: Path
    source: str
    size: int
    mime_type: str
    created_at: float
    expires_at: float


class ImageStagingPool:
    """按会话隔离的图片暂存池，采用惰性 TTL 过期机制。

    每个 conv_id 维护独立的 ``dict[str, StagedImage]``。
    键为 8 位十六进制字符串，仅在会话内部唯一。
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._pools: dict[str, dict[str, StagedImage]] = {}
        self._ttl = ttl_seconds

    @property
    def ttl(self) -> int:
        """TTL 时长（秒）。"""
        return self._ttl

    def put(
        self,
        conv_id: str,
        file_path: Path,
        *,
        key: str | None = None,
        source: str = "",
    ) -> str:
        """将图片存入 *conv_id* 对应的暂存池，返回分配的键。

        若 *key* 为 ``None``，则自动生成 8 位十六进制键。
        """
        self._cleanup_expired(conv_id)
        if conv_id not in self._pools:
            self._pools[conv_id] = {}

        if key is None:
            key = secrets.token_hex(4)

        mime = mimetypes.guess_type(str(file_path))[0] or "image/png"
        size = file_path.stat().st_size if file_path.exists() else 0
        now = time.monotonic()

        self._pools[conv_id][key] = StagedImage(
            key=key,
            file_path=file_path,
            source=source,
            size=size,
            mime_type=mime,
            created_at=now,
            expires_at=now + self._ttl,
        )
        return key

    def get(self, conv_id: str, key: str) -> StagedImage | None:
        """按键获取已暂存的图片，过期或不存在时返回 ``None``。"""
        self._cleanup_expired(conv_id)
        pool = self._pools.get(conv_id)
        if pool is None:
            return None
        return pool.get(key)

    def list(self, conv_id: str) -> list[StagedImage]:
        """列出 *conv_id* 下所有有效的暂存图片（新的在前）。"""
        self._cleanup_expired(conv_id)
        pool = self._pools.get(conv_id)
        if pool is None:
            return []
        return sorted(pool.values(), key=lambda x: x.created_at, reverse=True)

    def remove(self, conv_id: str, key: str) -> bool:
        """移除指定图片，成功移除时返回 ``True``。"""
        pool = self._pools.get(conv_id)
        if pool is None:
            return False
        return pool.pop(key, None) is not None

    def clear(self, conv_id: str) -> int:
        """清空某会话的所有图片，返回移除数量。"""
        pool = self._pools.pop(conv_id, None)
        if pool is None:
            return 0
        return len(pool)

    def clear_all(self) -> int:
        """清空所有暂存池，返回移除的总数量。"""
        total = sum(len(pool) for pool in self._pools.values())
        self._pools.clear()
        return total

    def _cleanup_expired(self, conv_id: str) -> int:
        pool = self._pools.get(conv_id)
        if pool is None:
            return 0
        now = time.monotonic()
        expired = [key for key, img in pool.items() if now - img.created_at > self._ttl]
        for key in expired:
            del pool[key]
        return len(expired)
