"""Image staging pool — per-conversation in-memory image cache with TTL."""

from __future__ import annotations

import mimetypes
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StagedImage:
    """A single staged image entry."""

    key: str
    file_path: Path
    source: str
    size: int
    mime_type: str
    created_at: float
    expires_at: float


class ImageStagingPool:
    """Per-conversation image staging pool with lazy TTL expiration.

    Each conv_id maintains an independent ``dict[str, StagedImage]``.
    Keys are 8-char hex strings, unique only within the conversation.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._pools: dict[str, dict[str, StagedImage]] = {}
        self._ttl = ttl_seconds

    @property
    def ttl(self) -> int:
        """TTL in seconds."""
        return self._ttl

    def put(
        self,
        conv_id: str,
        file_path: Path,
        *,
        key: str | None = None,
        source: str = "",
    ) -> str:
        """Store an image in the pool for *conv_id*. Returns the assigned key.

        If *key* is ``None``, an 8-character hex key is auto-generated.
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
        """Get a staged image by key. Returns ``None`` if expired or missing."""
        self._cleanup_expired(conv_id)
        pool = self._pools.get(conv_id)
        if pool is None:
            return None
        return pool.get(key)

    def list(self, conv_id: str) -> list[StagedImage]:
        """List all valid staged images for *conv_id* (newest first)."""
        self._cleanup_expired(conv_id)
        pool = self._pools.get(conv_id)
        if pool is None:
            return []
        return sorted(pool.values(), key=lambda x: x.created_at, reverse=True)

    def remove(self, conv_id: str, key: str) -> bool:
        """Remove a specific image. Returns ``True`` if it was removed."""
        pool = self._pools.get(conv_id)
        if pool is None:
            return False
        return pool.pop(key, None) is not None

    def clear(self, conv_id: str) -> int:
        """Clear all images for a conversation. Returns the count removed."""
        pool = self._pools.pop(conv_id, None)
        if pool is None:
            return 0
        return len(pool)

    def clear_all(self) -> int:
        """Clear all pools. Returns the total count removed."""
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
