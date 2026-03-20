"""Memory 服务装配"""

from __future__ import annotations

from neobot_contracts.ports.clock import Clock, SystemClock
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.repository import MemoryRepository

from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository


def build_memory_service(
    *,
    repository: MemoryRepository | None = None,
    logger: Logger | None = None,
    clock: Clock | None = None,
) -> MemoryService:
    return MemoryService(
        repository=repository or InMemoryMemoryRepository(),
        logger=logger or NullLogger(),
        clock=clock or SystemClock(),
    )
