"""Creator image gallery access port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from neobot_contracts.models.memory import CreatorImageRecord


@runtime_checkable
class CreatorImageAccess(Protocol):
    """Persistence access for Creator Agent images."""

    async def get(self, image_id: str) -> Optional[CreatorImageRecord]: ...

    async def set(
        self,
        image_id: str,
        *,
        source: str,
        file_hash: str,
        file_path: str,
        prompt: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
    ) -> CreatorImageRecord: ...

    async def delete(self, image_id: str) -> bool: ...

    async def count(self, *, source: Optional[str] = None) -> int: ...

    async def list(
        self,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]: ...

    async def search(
        self,
        keyword: str,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]: ...
