"""Emoji analysis cache access port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from neobot_contracts.models.memory import EmojiRecord


@runtime_checkable
class EmojiAccess(Protocol):
    """Persistence access for cached emoji analysis results."""

    async def get_by_hash(self, file_hash: str) -> Optional[EmojiRecord]: ...

    async def get_by_file_name(self, file_name: str) -> Optional[EmojiRecord]: ...

    async def set(
        self,
        file_hash: str,
        *,
        file_name: str,
        file_path: str,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        analysis_text: Optional[str] = None,
        image_source: Optional[str] = None,
    ) -> EmojiRecord: ...

    async def delete(self, file_hash: str) -> bool: ...

    async def rename(
        self, file_hash: str, *, new_file_name: str, new_file_path: str
    ) -> EmojiRecord: ...

    async def list_all(self) -> list[EmojiRecord]: ...

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by_use_count: bool = False,
    ) -> list[EmojiRecord]: ...

    async def search(
        self,
        keyword: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmojiRecord]: ...

    async def increment_usage(self, file_hash: str) -> None: ...

    async def count(self) -> int: ...
