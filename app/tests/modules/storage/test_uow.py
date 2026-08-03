"""SqlAlchemyUnitOfWork 测试: 提交、异常回滚、重复 commit、锁冲突重试恢复 session。"""

from __future__ import annotations

import asyncio
import random

import aiosqlite
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_contracts.time_context import now_utc
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory


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


@pytest.mark.xfail(
    reason=(
        "BUG-001: UoW.commit 的 retry_on_lock 在 flush 阶段锁冲突后调用 "
        "session.rollback 丢弃了待持久化对象，重试的 commit 为空事务，"
        "数据静默丢失（已实测复现）"
    ),
    strict=False,
)
async def test_uow_commit_retries_and_persists_after_lock_contention(tmp_path, monkeypatch):
    """锁冲突导致 flush 失败时，commit 重试后 on_retry 恢复 session 且数据必须完整落库。"""

    # Arrange: 短 busy_timeout 引擎 + 持写锁的连接, 禁用随机抖动使时序确定
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
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        factory = make_uow_factory(engine)

        async def release_lock() -> None:
            await asyncio.sleep(0.6)
            await locker.commit()

        release_task = asyncio.create_task(release_lock())

        # Act
        async with factory() as uow:
            await uow.messages.save_message(_make_message("e1"))
            await uow.commit()
        await release_task

        # Assert
        async with factory() as reader:
            history = await reader.messages.get_history(
                ConversationRef(kind="private", id="c1"), limit=50
            )
            assert [m.event_id for m in history] == ["e1"]
    finally:
        if locker is not None:
            await locker.commit()
            await locker.close()
        await engine.dispose()
