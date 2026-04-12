"""Memory 服务装配"""

from __future__ import annotations

from neobot_contracts.ports.clock import Clock, SystemClock
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.repository import MemoryRepository
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory

from neobot_memory import ArchiveMemoryService, ImageAnalysisService, MemoryService
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


def build_archive_memory_service(
    *,
    uow_factory: UnitOfWorkFactory,
    logger: Logger | None = None,
) -> ArchiveMemoryService:
    return ArchiveMemoryService(
        uow_factory=uow_factory,
        logger=logger or NullLogger(),
    )


def build_image_analysis_service(
    *,
    uow_factory: UnitOfWorkFactory,
    logger: Logger | None = None,
) -> ImageAnalysisService:
    return ImageAnalysisService(
        uow_factory=uow_factory,
        logger=logger or NullLogger(),
    )
