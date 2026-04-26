"""UnitOfWork Port — 工作单元抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from neobot_contracts.ports.archive_memory_access import ArchiveMemoryAccess
from neobot_contracts.ports.creator_image_access import CreatorImageAccess
from neobot_contracts.ports.emoji_access import EmojiAccess
from neobot_contracts.ports.image_analysis_access import ImageAnalysisAccess
from neobot_contracts.ports.repository import MemoryRepository, MessageRepository, ProfileRepository


@runtime_checkable
class UnitOfWork(Protocol):
    """工作单元接口，管理一次事务中的多个 Repository"""

    messages: MessageRepository
    memories: MemoryRepository
    profiles: ProfileRepository
    archive: ArchiveMemoryAccess  # 档案式记忆访问接口
    images: ImageAnalysisAccess
    emojis: EmojiAccess
    creator_images: CreatorImageAccess

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, *exc: object) -> None: ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    """工作单元工厂接口"""

    def __call__(self) -> UnitOfWork: ...
