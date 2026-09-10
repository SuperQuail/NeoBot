"""SqlAlchemyUnitOfWork —— 实现 contracts 定义的 UnitOfWork 接口。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from neobot_contracts.ports.unit_of_work import UnitOfWork

from neobot_storage._retry import _is_locked_error
from neobot_storage.repositories.memory import SqlAlchemyMemoryRepository
from neobot_storage.repositories.message import SqlAlchemyMessageRepository
from neobot_storage.repositories.profile import SqlAlchemyProfileRepository
from neobot_storage.repositories.archive import SqlAlchemyArchiveMemoryAccess
from neobot_storage.repositories.creator_image import SqlAlchemyCreatorImageAccess
from neobot_storage.repositories.image import SqlAlchemyImageAnalysisAccess
from neobot_storage.repositories.emoji import SqlAlchemyEmojiAccess
from neobot_storage.repositories.scheduled_task import SqlAlchemyScheduledTaskAccess


class SqlAlchemyUnitOfWork:
    """基于 SQLAlchemy AsyncSession 的异步工作单元。"""

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
        """提交事务；锁冲突一律显式失败。

        ``retry_on_lock`` 的正确用法是让**调用方重放整个事务体**
        （见 ``statistics/tracker.py``），而不是 rollback 之后重试 ``commit()``：
        后者会把已经发往数据库的 Core DML 连同事务一起丢掉，在 commit 成功
        返回的同时静默丢失写入——仓库层大量使用
        ``session.execute(insert(...).on_conflict_do_update())``，这类写入
        不会体现在 ORM 的 new/dirty/deleted 状态里，因此不能靠
        ``session._proxied._is_clean()``（私有 API）判断「提交是空操作」。
        """
        try:
            await self._session.commit()
        except Exception as exc:
            if not _is_locked_error(exc):
                raise
            await self._session.rollback()
            raise RuntimeError(
                "事务因锁冲突已回滚，写入未持久化，请重试整个事务"
            ) from exc

    async def rollback(self) -> None:
        await self._session.rollback()


def make_uow_factory(engine: AsyncEngine):
    """返回一个可生成 SqlAlchemyUnitOfWork 实例的可调用对象。"""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory
