"""Repository Ports — 数据持久化抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

from neobot_contracts.models import ConversationRef, IncomingMessage, MemoryRecord


@runtime_checkable
class MemoryRepository(Protocol):
    """记忆存储接口"""

    async def save(self, record: MemoryRecord) -> None: ...
    async def search(
        self, conversation: ConversationRef, query: str, limit: int = 5
    ) -> list[MemoryRecord]: ...


@runtime_checkable
class MessageRepository(Protocol):
    """消息存储接口"""

    async def save_message(self, message: IncomingMessage) -> None: ...
    async def get_history(
        self, conversation: ConversationRef, limit: int = 50
    ) -> list[IncomingMessage]: ...


@runtime_checkable
class ProfileRepository(Protocol):
    """用户/群资料存储接口"""

    async def upsert_user(self, user_id: str, **fields) -> None: ...
    async def upsert_group(self, group_id: str, **fields) -> None: ...
    async def user_exists(self, user_id: str) -> bool: ...
    async def group_exists(self, group_id: str) -> bool: ...
    async def get_user(self, user_id: str) -> Any | None: ...
    async def get_group(self, group_id: str) -> Any | None: ...
