"""SqlAlchemyUnitOfWork — implements contracts.UnitOfWork."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from neobot_contracts.ports.unit_of_work import UnitOfWork

from neobot_storage.repositories.memory import SqlAlchemyMemoryRepository
from neobot_storage.repositories.message import SqlAlchemyMessageRepository
from neobot_storage.repositories.profile import SqlAlchemyProfileRepository
from neobot_storage.repositories.archive import SqlAlchemyArchiveMemoryAccess
from neobot_storage.repositories.creator_image import SqlAlchemyCreatorImageAccess
from neobot_storage.repositories.image import SqlAlchemyImageAnalysisAccess
from neobot_storage.repositories.emoji import SqlAlchemyEmojiAccess
from neobot_storage.repositories.scheduled_task import SqlAlchemyScheduledTaskAccess


class SqlAlchemyUnitOfWork:
    """Async unit of work backed by a SQLAlchemy AsyncSession."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session: AsyncSession = self._factory()
        self.messages = SqlAlchemyMessageRepository(self._session)
        self.memories = SqlAlchemyMemoryRepository(self._session)
        self.profiles = SqlAlchemyProfileRepository(self._session)
        self.archive = SqlAlchemyArchiveMemoryAccess(self._session)
        self.images = SqlAlchemyImageAnalysisAccess(self._session)
        self.emojis = SqlAlchemyEmojiAccess(self._session)
        self.creator_images = SqlAlchemyCreatorImageAccess(self._session)
        self.scheduled_tasks = SqlAlchemyScheduledTaskAccess(self._session)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if exc[0] is not None:
            await self.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def make_uow_factory(engine: AsyncEngine):
    """Return a callable that produces SqlAlchemyUnitOfWork instances."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory
