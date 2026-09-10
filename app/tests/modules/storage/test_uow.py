"""SqlAlchemyUnitOfWork 测试: 提交、异常回滚、重复 commit、锁冲突重试恢复 session。"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_contracts.time_context import now_utc
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import SqlAlchemyUnitOfWork, make_uow_factory


@pytest_asyncio.fixture
async def engine(tmp_path):
    """每用例独立的临时 sqlite 引擎 (WAL + busy_timeout, 与生产一致)。"""
    eng = create_engine(sqlite_url(tmp_path / "uow.db"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def uow_factory(engine):
    """基于独立引擎的 UoW 工厂。"""
    return make_uow_factory(engine)


def _make_message(event_id: str, text_body: str = "hello") -> IncomingMessage:
    """构造一条待持久化的入站消息。"""
    return IncomingMessage(
        event_id=event_id,
        conversation=ConversationRef(kind="private", id="c1"),
        sender_id="s1",
        sender_name="S",
        text=text_body,
        occurred_at=now_utc(),
    )


async def test_uow_commit_persists_changes(uow_factory):
    """在 UoW 上下文中写入并 commit 后，新 UoW 必须能读到持久化数据。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.profiles.upsert_user("u1", nick_name="娜娜")

        # Act
        await uow.commit()

    # Assert
    async with uow_factory() as reader:
        assert await reader.profiles.user_exists("u1")


async def test_uow_context_exit_rolls_back_on_exception(uow_factory):
    """with 块内抛异常时退出上下文必须自动回滚，不留下任何数据。"""

    # Arrange / Act
    with pytest.raises(ValueError):
        async with uow_factory() as uow:
            await uow.profiles.upsert_user("u1", nick_name="娜娜")
            raise ValueError("boom")

    # Assert
    async with uow_factory() as reader:
        assert not await reader.profiles.user_exists("u1")


async def test_uow_explicit_rollback_discards_pending_changes(uow_factory):
    """显式 rollback 后再 commit 必须丢弃全部未提交变更。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.profiles.upsert_user("u1", nick_name="娜娜")

        # Act
        await uow.rollback()
        await uow.commit()

    # Assert
    async with uow_factory() as reader:
        assert not await reader.profiles.user_exists("u1")


async def test_uow_repeated_commit_is_harmless(uow_factory):
    """对同一 UoW 连续 commit 两次不得抛异常且数据只写入一份。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.messages.save_message(_make_message("e1"))

        # Act
        await uow.commit()
        await uow.commit()

    # Assert
    async with uow_factory() as reader:
        history = await reader.messages.get_history(
            ConversationRef(kind="private", id="c1"), limit=50
        )
        assert [m.event_id for m in history] == ["e1"]


async def test_uow_factory_produces_independent_sessions(uow_factory):
    """同一工厂创建的两个 UoW 必须互不干扰，各自提交各自的数据。"""

    # Arrange
    async def write_user(user_id: str, name: str) -> None:
        async with uow_factory() as uow:
            await uow.profiles.upsert_user(user_id, nick_name=name)
            await uow.commit()

    # Act
    await asyncio.gather(write_user("u1", "甲"), write_user("u2", "乙"))

    # Assert
    async with uow_factory() as reader:
        assert await reader.profiles.user_exists("u1")
        assert await reader.profiles.user_exists("u2")


async def test_uow_commit_flush_lock_conflict_raises_without_silent_loss(tmp_path):
    """flush 阶段锁冲突时 commit 必须显式抛错，且不得静默成功留下空事务。"""

    # Arrange: 短 busy_timeout 引擎 + 持写锁的连接
    db = tmp_path / "locked.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db.as_posix()}", connect_args={"timeout": 0.2}
    )
    locker = None
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        locker = await aiosqlite.connect(db.as_posix())
        await locker.execute("BEGIN IMMEDIATE")
        await locker.execute("INSERT INTO user_data (user_id, favorability) VALUES ('locker', 0)")
        factory = make_uow_factory(engine)

        async def release_lock() -> None:
            await asyncio.sleep(0.6)
            await locker.commit()

        release_task = asyncio.create_task(release_lock())

        # Act: 写操作因写锁在 flush 阶段失败，写入已丢失
        async with factory() as uow:
            await uow.messages.save_message(_make_message("e1"))
            with pytest.raises(RuntimeError, match="未持久化"):
                await uow.commit()
        await release_task

        # Assert: 显式失败而非静默成功，消息不得被持久化
        async with factory() as reader:
            history = await reader.messages.get_history(
                ConversationRef(kind="private", id="c1"), limit=50
            )
            assert history == []
    finally:
        if locker is not None:
            await locker.commit()
            await locker.close()
        await engine.dispose()


async def test_uow_commit_phase_lock_conflict_also_fails_loudly():
    """commit 阶段的锁冲突同样必须显式失败，不得 rollback 后重试 commit。

    旧实现对「ORM 状态干净」的会话先 rollback 再重试 commit：仓库层大量使用
    Core DML（``session.execute(insert(...).on_conflict_do_update())``），这类
    写入不体现在 ORM 状态里，会被判成「干净」，于是重试 commit 会提交一个
    空事务并成功返回——写入静默丢失。
    """

    class _FlakySession:
        def __init__(self) -> None:
            self.attempts = 0
            self.rollbacks = 0

        async def commit(self) -> None:
            self.attempts += 1
            raise OperationalError("COMMIT", (), Exception("database is locked"))

        async def rollback(self) -> None:
            self.rollbacks += 1

        async def close(self) -> None:
            pass

    uow = SqlAlchemyUnitOfWork(lambda: _FlakySession())
    await uow.__aenter__()
    try:
        with pytest.raises(RuntimeError, match="未持久化"):
            await uow.commit()
    finally:
        await uow.__aexit__(None, None, None)

    assert uow._session.attempts == 1
    assert uow._session.rollbacks == 1
