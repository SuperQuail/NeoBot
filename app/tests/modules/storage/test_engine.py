"""neobot_storage.engine 测试: 引擎创建、SQLite WAL/busy_timeout、dispose、URL 归一化、迁移。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from neobot_storage.engine import create_engine, run_migrations, sqlite_url


async def test_create_engine_returns_sqlite_async_engine(tmp_path):
    """创建 sqlite 引擎后必须返回可用的 AsyncEngine 且后端为 sqlite。"""

    # Arrange
    db = tmp_path / "engine.db"

    # Act
    engine = create_engine(sqlite_url(db))

    # Assert
    assert isinstance(engine, AsyncEngine)
    assert engine.url.get_backend_name() == "sqlite"
    await engine.dispose()


async def test_sqlite_engine_enables_wal_journal_mode(tmp_path):
    """生产引擎连接 sqlite 后 PRAGMA journal_mode 必须是 wal。"""

    # Arrange
    engine = create_engine(sqlite_url(tmp_path / "wal.db"))

    # Act
    async with engine.connect() as conn:
        mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()

    # Assert
    assert mode == "wal"
    await engine.dispose()


async def test_sqlite_engine_sets_busy_timeout(tmp_path):
    """生产引擎连接 sqlite 后 busy_timeout 必须为 5000ms。"""

    # Arrange
    engine = create_engine(sqlite_url(tmp_path / "busy.db"))

    # Act
    async with engine.connect() as conn:
        timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()

    # Assert
    assert timeout == 5000
    await engine.dispose()


async def test_engine_dispose_is_idempotent_and_releases_connections(tmp_path):
    """dispose 释放连接池且可重复调用而不抛异常。"""

    # Arrange
    engine = create_engine(sqlite_url(tmp_path / "dispose.db"))
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.close()
    assert engine.sync_engine.pool.checkedout() == 0

    # Act
    await engine.dispose()
    await engine.dispose()

    # Assert
    assert engine.sync_engine.pool.checkedout() == 0


def test_sqlite_url_builds_absolute_posix_url(tmp_path):
    """sqlite_url 必须返回 sqlite+aiosqlite 前缀且路径为绝对 posix 路径。"""

    # Arrange
    db = tmp_path / "data" / "x.db"

    # Act
    url = sqlite_url(db)

    # Assert
    assert url.startswith("sqlite+aiosqlite:///")
    assert url.endswith("/x.db")
    assert "\\" not in url


async def test_run_migrations_applies_full_schema(tmp_path):
    """run_migrations 对全新 sqlite 库执行后必须建出全部核心表。"""

    # Arrange
    db = tmp_path / "migrated.db"
    url = sqlite_url(db)
    expected = {
        "user_data",
        "messages",
        "memories",
        "archive_memories",
        "images",
        "emojis",
        "creator_images",
        "scheduled_tasks",
        "completed_scheduled_tasks",
        "model_usage_records",
        "bilibili_links",
        "maintenance_runs",
    }

    # Act
    run_migrations(url)
    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            ).all()

        # Assert
        names = {row[0] for row in rows}
        assert expected <= names
    finally:
        await engine.dispose()


async def test_create_engine_rejects_nonexistent_sqlite_path(tmp_path):
    """向不存在的父目录创建 sqlite 库时必须抛出异常。"""

    # Arrange
    url = f"sqlite+aiosqlite:///{tmp_path / 'no_such_dir' / 'x.db'}"
    engine = create_engine(url)

    # Act / Assert
    with pytest.raises(Exception):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    await engine.dispose()


def test_sqlite_url_is_idempotent_for_same_path(tmp_path: Path) -> None:
    """sqlite_url 对同一路径重复调用必须幂等。"""

    # Arrange
    db = tmp_path / "idempotent.db"

    # Act
    first = sqlite_url(db)
    second = sqlite_url(db)

    # Assert
    assert first == second
