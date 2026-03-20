"""UnitOfWork Port — 工作单元抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from neobot_contracts.ports.repository import MemoryRepository, MessageRepository


@runtime_checkable
class UnitOfWork(Protocol):
    """工作单元协议，管理一次事务中的多个 Repository"""

    messages: MessageRepository
    memories: MemoryRepository

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, *exc: object) -> None: ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    """工作单元工厂协议"""

    def __call__(self) -> UnitOfWork: ...
