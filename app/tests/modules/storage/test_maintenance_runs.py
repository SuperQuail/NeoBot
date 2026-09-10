"""neobot_storage 沙箱维护运行记录测试: 模型读写、仓储查询与迁移。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_contracts.time_context import now_utc
from neobot_storage.engine import create_engine, run_migrations, sqlite_url
from neobot_storage.models import Base, MaintenanceRunRecord
from neobot_storage.repositories.maintenance import SqlAlchemyMaintenanceRunRepository


@pytest_asyncio.fixture
async def engine(tmp_path):
    """每用例独立的临时 sqlite 引擎 (WAL + busy_timeout, 与生产一致)。"""
    eng = create_engine(sqlite_url(tmp_path / "maintenance.db"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _record(
    *,
    started_at,
    status: str = "success",
    trigger: str = "interval",
    tool_calls: int = 0,
    finished_at=None,
    summary: str | None = None,
    error: str | None = None,
    skipped_reason: str | None = None,
) -> MaintenanceRunRecord:
    return MaintenanceRunRecord(
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        trigger=trigger,
        tool_calls=tool_calls,
        summary=summary,
        error=error,
        skipped_reason=skipped_reason,
    )


async def test_maintenance_run_roundtrip_persists_all_fields(session_factory):
    """写入一条维护运行记录后必须能逐字段读回。"""

    # Arrange
    started = now_utc()
    finished = started + timedelta(minutes=3)

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        await repo.add(
            _record(
                started_at=started,
                finished_at=finished,
                status="failed",
                trigger="manual",
                tool_calls=7,
                summary="清理临时目录",
                error="沙箱不可用",
                skipped_reason=None,
            )
        )
        await session.commit()

    # Assert
    async with session_factory() as session:
        stored = (
            await session.execute(select(MaintenanceRunRecord))
        ).scalars().one()
    assert stored.id is not None
    # DateTime 列不带时区(与 ModelUsageRecord 一致)，读回时 tzinfo 会被丢弃
    assert stored.started_at == started.replace(tzinfo=None)
    assert stored.finished_at == finished.replace(tzinfo=None)
    assert stored.status == "failed"
    assert stored.trigger == "manual"
    assert stored.tool_calls == 7
    assert stored.summary == "清理临时目录"
    assert stored.error == "沙箱不可用"
    assert stored.skipped_reason is None


async def test_maintenance_run_running_row_has_no_finished_at_and_default_tool_calls(session_factory):
    """running 记录允许 finished_at 为空，tool_calls 未指定时默认 0。"""

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        await repo.add(
            _record(started_at=now_utc(), status="running", trigger="startup")
        )
        await session.commit()

    # Assert
    async with session_factory() as session:
        stored = (
            await session.execute(select(MaintenanceRunRecord))
        ).scalars().one()
    assert stored.finished_at is None
    assert stored.tool_calls == 0


async def test_latest_orders_by_started_at_desc_and_respects_limit(session_factory):
    """latest 必须按 started_at 降序返回并遵守 limit。"""

    # Arrange
    base = now_utc()
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        for index in range(5):
            await repo.add(
                _record(started_at=base + timedelta(hours=index), tool_calls=index)
            )
        await session.commit()

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        all_runs = await repo.latest()
        limited = await repo.latest(limit=2)

    # Assert
    assert [r.tool_calls for r in all_runs] == [4, 3, 2, 1, 0]
    assert [r.tool_calls for r in limited] == [4, 3]


async def test_last_finished_success_skips_failed_running_and_skipped(session_factory):
    """last_finished_success 只认 success, 且取其中 started_at 最大的一条。"""

    # Arrange
    base = now_utc()
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        await repo.add(_record(started_at=base, status="success", tool_calls=1))
        await repo.add(
            _record(started_at=base + timedelta(hours=1), status="success", tool_calls=2)
        )
        await repo.add(
            _record(started_at=base + timedelta(hours=2), status="failed", tool_calls=3)
        )
        await repo.add(
            _record(started_at=base + timedelta(hours=3), status="running", tool_calls=4)
        )
        await repo.add(
            _record(
                started_at=base + timedelta(hours=4),
                status="skipped",
                tool_calls=0,
                skipped_reason="距上次维护不足间隔",
            )
        )
        await session.commit()

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        last_success = await repo.last_finished_success()
        last_attempt = await repo.last_attempt()

    # Assert
    assert last_success is not None
    assert last_success.status == "success"
    assert last_success.tool_calls == 2
    # last_attempt 取任意状态里最新的一条(skipped 也算一次尝试)
    assert last_attempt is not None
    assert last_attempt.status == "skipped"
    assert last_attempt.tool_calls == 0


async def test_last_queries_return_none_on_empty_table(session_factory):
    """空表时 last_finished_success 与 last_attempt 必须返回 None。"""

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        last_success = await repo.last_finished_success()
        last_attempt = await repo.last_attempt()
        latest = await repo.latest()

    # Assert
    assert last_success is None
    assert last_attempt is None
    assert latest == []


async def test_last_finished_success_returns_none_when_all_failed(session_factory):
    """只有失败记录时 last_finished_success 必须返回 None。"""

    # Arrange
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        await repo.add(_record(started_at=now_utc(), status="failed", error="boom"))
        await session.commit()

    # Act
    async with session_factory() as session:
        repo = SqlAlchemyMaintenanceRunRepository(session)
        assert await repo.last_finished_success() is None
        assert (await repo.last_attempt()) is not None


async def test_migrations_build_maintenance_runs_schema(tmp_path):
    """run_migrations 必须建出 maintenance_runs 表、全部列与两个索引。"""

    # Arrange
    db = tmp_path / "migrated_maintenance.db"
    url = sqlite_url(db)

    # Act
    run_migrations(url)
    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            tables = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            ).all()
            indexes = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            ).all()
            columns = (await conn.execute(text("PRAGMA table_info(maintenance_runs)"))).all()
    finally:
        await engine.dispose()

    # Assert
    assert "maintenance_runs" in {row[0] for row in tables}
    assert {"ix_maintenance_runs_started_at", "ix_maintenance_runs_status"} <= {
        row[0] for row in indexes
    }
    assert {row[1] for row in columns} == {
        "id",
        "started_at",
        "finished_at",
        "status",
        "trigger",
        "tool_calls",
        "summary",
        "error",
        "skipped_reason",
    }
    not_null = {row[1] for row in columns if row[3]}
    assert not_null == {"id", "started_at", "status", "trigger", "tool_calls"}


async def test_migration_downgrade_drops_maintenance_runs(tmp_path):
    """downgrade 到 0021 必须删掉 maintenance_runs 表与索引。"""

    # Arrange
    from alembic import command
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    db = tmp_path / "downgraded.db"
    url = sqlite_url(db)
    run_migrations(url)

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))

    # Act
    command.downgrade(cfg, "0021")

    # Assert
    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            tables = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            ).all()
            indexes = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            ).all()
    finally:
        await engine.dispose()

    names = {row[0] for row in tables}
    index_names = {row[0] for row in indexes}
    assert "maintenance_runs" not in names
    assert "ix_maintenance_runs_started_at" not in index_names
    assert "ix_maintenance_runs_status" not in index_names
    # 其它表不受影响
    assert "model_usage_records" in names
