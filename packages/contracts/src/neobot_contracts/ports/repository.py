"""Repository Ports — 数据持久化抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef, IncomingMessage, MemoryRecord


@runtime_checkable
class MemoryRepository(Protocol):
    """记忆存储协议"""

    async def save(self, record: MemoryRecord) -> None: ...
    async def search(
        self, conversation: ConversationRef, query: str, limit: int = 5
    ) -> list[MemoryRecord]: ...


@runtime_checkable
class MessageRepository(Protocol):
    """消息存储协议"""

    async def save_message(self, message: IncomingMessage) -> None: ...
    async def get_history(
        self, conversation: ConversationRef, limit: int = 50
    ) -> list[IncomingMessage]: ...
