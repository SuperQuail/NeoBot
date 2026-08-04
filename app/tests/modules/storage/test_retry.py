from __future__ import annotations

import asyncio

import aiosqlite
import pytest
from sqlalchemy import String, text
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from neobot_storage._retry import _is_locked_error, retry_on_lock


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


async def _engine_and_locker(tmp_path, name: str):
    db = tmp_path / f"{name}.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    locker = await aiosqlite.connect(db.as_posix())
    await locker.execute("BEGIN IMMEDIATE")
    await locker.execute("INSERT INTO items (name) VALUES ('holder')")
    return engine, locker


@pytest.mark.asyncio
async def test_retry_on_lock_persists_data_after_write_lock_contention(tmp_path):
    engine, locker = await _engine_and_locker(tmp_path, "contention")
    try:
        session = async_sessionmaker(engine, expire_on_commit=False)()
        try:
            async def release_locker() -> None:
                await asyncio.sleep(0.35)
                await locker.commit()

            release_task = asyncio.create_task(release_locker())

            async def flush_attempt() -> None:
                session.add(Item(name="retried"))
                await session.commit()

            await retry_on_lock(
                flush_attempt,
                max_retries=5,
                base_delay=0.05,
                max_delay=0.15,
                on_retry=session.rollback,
            )
            await release_task

            async with engine.connect() as conn:
                rows = (await conn.execute(text("SELECT name FROM items ORDER BY id"))).all()
            assert [row[0] for row in rows] == ["holder", "retried"]
        finally:
            await session.close()
    finally:
        await locker.commit()
        await locker.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_rollback_error_from_locked_flush_is_detected(tmp_path):
    engine, locker = await _engine_and_locker(tmp_path, "pending")
    try:
        session = async_sessionmaker(engine, expire_on_commit=False)()
        try:
            session.add(Item(name="x"))
            with pytest.raises(OperationalError) as excinfo:
                await session.commit()
            assert _is_locked_error(excinfo.value)

            with pytest.raises(PendingRollbackError) as excinfo2:
                await session.commit()
            assert "rolled back" in str(excinfo2.value)
            assert _is_locked_error(excinfo2.value)
        finally:
            await session.close()
    finally:
        await locker.commit()
        await locker.close()
        await engine.dispose()


def test_non_lock_errors_are_not_retried():
    assert not _is_locked_error(Exception("transaction rolled back, constraint violated"))
    assert not _is_locked_error(ValueError("bad value"))


@pytest.mark.asyncio
async def test_on_retry_invoked_before_each_retry():
    attempts = 0
    rollbacks = 0

    async def attempt() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OperationalError(
                "INSERT INTO items (name) VALUES (?)",
                ("x",),
                Exception("database is locked"),
            )

    async def on_retry() -> None:
        nonlocal rollbacks
        rollbacks += 1

    await retry_on_lock(
        attempt,
        max_retries=3,
        base_delay=0.01,
        max_delay=0.01,
        on_retry=on_retry,
    )
    assert attempts == 3
    assert rollbacks == 2


@pytest.mark.asyncio
async def test_retry_on_lock_raises_last_error_when_retries_exhausted():
    """锁错误持续发生时, 重试次数耗尽后必须抛出最后一次遇到的异常。"""

    # Arrange
    attempts = 0
    rollbacks = 0
    last_error = OperationalError(
        "INSERT INTO items (name) VALUES (?)",
        ("x",),
        Exception("database is locked"),
    )

    async def attempt() -> None:
        nonlocal attempts
        attempts += 1
        raise last_error

    async def on_retry() -> None:
        nonlocal rollbacks
        rollbacks += 1

    # Act
    with pytest.raises(OperationalError) as excinfo:
        await retry_on_lock(
            attempt,
            max_retries=2,
            base_delay=0.001,
            max_delay=0.001,
            on_retry=on_retry,
        )

    # Assert
    assert excinfo.value is last_error
    assert attempts == 3
    assert rollbacks == 2


@pytest.mark.asyncio
async def test_retry_on_lock_returns_value_after_transient_failure():
    """首次尝试锁失败、重试成功时必须返回成功那次的结果。"""

    # Arrange
    attempts = 0

    async def attempt() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(
                "INSERT INTO items (name) VALUES (?)",
                ("x",),
                Exception("database is locked"),
            )
        return 42

    # Act
    result = await retry_on_lock(attempt, max_retries=3, base_delay=0.001, max_delay=0.001)

    # Assert
    assert result == 42
    assert attempts == 2
