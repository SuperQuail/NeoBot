"""压缩前快照表 archive_snapshots 的存储层与迁移测试（spec(4) Part C / D15 / A41）。

覆盖：
- 仓库 add / list / get / delete 基本语义；
- A41：同一 (table_name, key) 连写 12 次后只剩最近 10 份（最旧被删）+ 全局兜底上限；
- 服务层 save_snapshot / list_snapshots / get_snapshot / delete_snapshot / prune_snapshots；
- 迁移 0026 的 upgrade / downgrade 往返（新增表，不丢档案数据）。
"""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from neobot_contracts.ports.logging import NullLogger
from neobot_memory.archive_service import (
    MAX_ARCHIVE_SNAPSHOTS,
    MAX_ARCHIVE_SNAPSHOTS_PER_KEY,
    ArchiveMemoryService,
)
from neobot_storage.repositories.archive_snapshot import (
    DEFAULT_MAX_SNAPSHOTS,
    DEFAULT_SNAPSHOTS_PER_KEY,
)
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema


@pytest_asyncio.fixture
async def uow_factory():
    engine = create_memory_engine()
    await create_schema(engine)
    try:
        yield make_uow_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def service(uow_factory):
    return ArchiveMemoryService(uow_factory=uow_factory, logger=NullLogger())


# ── 仓库层 ────────────────────────────────────────────────────────


async def test_uow_exposes_snapshot_access(uow_factory) -> None:
    async with uow_factory() as uow:
        assert hasattr(uow, "archive_snapshots")
        row = await uow.archive_snapshots.add(
            "user_profile", "1", "x" * 30, total_chars=30, version=3, reason="manual"
        )
        await uow.commit()
    assert row["id"] > 0
    assert row["total_chars"] == 30
    assert row["reason"] == "manual"
    assert row["value"] == "x" * 30


async def test_repository_list_get_delete_roundtrip(uow_factory) -> None:
    async with uow_factory() as uow:
        first = await uow.archive_snapshots.add("user_profile", "1", "v1", total_chars=2)
        await uow.archive_snapshots.add("user_profile", "1", "v2", total_chars=2)
        await uow.archive_snapshots.add("user_profile", "2", "other", total_chars=5)
        await uow.commit()

    async with uow_factory() as uow:
        rows = await uow.archive_snapshots.list("user_profile", "1")
        assert all("value" not in row for row in rows)  # 列表默认不带全文
        full = await uow.archive_snapshots.list("user_profile", "1", include_value=True)
        assert [row["value"] for row in full] == ["v2", "v1"]  # 新的在前

    async with uow_factory() as uow:
        detail = await uow.archive_snapshots.get(first["id"])
        assert detail is not None and detail["value"] == "v1"
        assert await uow.archive_snapshots.delete(first["id"]) is True
        assert await uow.archive_snapshots.delete(first["id"]) is False
        await uow.commit()
        assert await uow.archive_snapshots.count() == 2


async def test_repository_keeps_only_ten_per_key(uow_factory) -> None:
    """A41：同一 (table_name, key) 连写 12 次 → 只剩最近 10 份，最旧被删。"""
    async with uow_factory() as uow:
        for index in range(12):
            await uow.archive_snapshots.add(
                "user_profile", "1", f"v{index}", total_chars=index
            )
            await uow.archive_snapshots.prune("user_profile", "1")
        await uow.commit()

    assert DEFAULT_SNAPSHOTS_PER_KEY == 10
    assert MAX_ARCHIVE_SNAPSHOTS_PER_KEY == 10
    async with uow_factory() as uow:
        rows = await uow.archive_snapshots.list(
            "user_profile", "1", limit=100, include_value=True
        )
    assert len(rows) == 10
    assert [row["value"] for row in rows] == [f"v{index}" for index in range(11, 1, -1)]


async def test_repository_prune_global_cap(uow_factory) -> None:
    """全局兜底上限：不同 key 的快照也不能无限累积。"""
    async with uow_factory() as uow:
        for index in range(6):
            await uow.archive_snapshots.add("user_profile", f"k{index}", f"v{index}")
        removed = await uow.archive_snapshots.prune(max_total=4)
        await uow.commit()
    assert removed == 2
    async with uow_factory() as uow:
        assert await uow.archive_snapshots.count() == 4
    assert DEFAULT_MAX_SNAPSHOTS == MAX_ARCHIVE_SNAPSHOTS == 2000


# ── 服务层 ────────────────────────────────────────────────────────


async def test_service_save_snapshot_prunes_and_returns_id(service) -> None:
    ids = []
    for index in range(12):
        snapshot_id = await service.save_snapshot(
            "user_profile", "1", f"v{index}", reason="manual", operator_ip="127.0.0.1"
        )
        ids.append(snapshot_id)
    assert all(isinstance(value, int) and value for value in ids)

    rows = await service.list_snapshots("user_profile", "1", limit=50)
    assert len(rows) == 10
    assert rows[0]["total_chars"] == len("v11")
    assert rows[0]["reason"] == "manual"
    assert rows[0]["operator_ip"] == "127.0.0.1"
    assert rows[0]["created_at"]  # ISO8601 字符串
    assert "value" not in rows[0]

    detail = await service.get_snapshot(ids[-1])
    assert detail is not None and detail["value"] == "v11"


async def test_service_delete_and_prune_snapshots(service) -> None:
    snapshot_id = await service.save_snapshot("user_profile", "1", "hello")
    assert await service.delete_snapshot(snapshot_id) is True
    assert await service.delete_snapshot(snapshot_id) is False
    assert await service.list_snapshots("user_profile", "1") == []

    for index in range(4):
        await service.save_snapshot("user_profile", "2", f"v{index}")
    assert await service.prune_snapshots("user_profile", "2") == 0  # 未超 10 份
    assert len(await service.list_snapshots("user_profile", "2", limit=50)) == 4


async def test_service_degrades_without_snapshot_access() -> None:
    """存储替身没有快照表时：快照降级为不落盘，不影响档案读写。"""

    class _ArchiveOnly:
        def __init__(self) -> None:
            self.rows: dict[tuple[str, str], str] = {}

        async def get(self, table_name, key):
            return None

    class _Uow:
        def __init__(self) -> None:
            self.archive = _ArchiveOnly()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def commit(self) -> None:
            return None

    service = ArchiveMemoryService(
        uow_factory=lambda: _Uow(), logger=NullLogger()  # type: ignore[arg-type]
    )
    assert await service.save_snapshot("user_profile", "1", "x") is None
    assert await service.list_snapshots("user_profile", "1") == []
    assert await service.get_snapshot(1) is None
    assert await service.delete_snapshot(1) is False
    assert await service.prune_snapshots() == 0


# ── 迁移 0026 ─────────────────────────────────────────────────────


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _tables(db: Path) -> set[str]:
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def _columns(db: Path, table: str) -> set[str]:
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        connection.close()
    return {str(row[1]) for row in rows}


def test_migration_0026_round_trip(tmp_path: Path) -> None:
    """A41：0026 upgrade / downgrade 往返正常，且不动既有档案数据。"""
    from alembic import command
    from sqlalchemy import text

    from neobot_storage.engine import create_engine, sqlite_url

    db = tmp_path / "snapshots.db"
    url = sqlite_url(db)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0025")
    assert "archive_snapshots" not in _tables(db)

    command.upgrade(cfg, "head")
    assert "archive_snapshots" in _tables(db)
    assert {
        "id",
        "table_name",
        "key",
        "value",
        "total_chars",
        "version",
        "reason",
        "operator_ip",
        "created_at",
    } <= _columns(db, "archive_snapshots")

    # 往返：downgrade 干净移除该表（既有档案行不受影响）
    command.downgrade(cfg, "0025")
    assert "archive_snapshots" not in _tables(db)
    command.upgrade(cfg, "head")
    assert "archive_snapshots" in _tables(db)

    import asyncio

    async def _write() -> None:
        engine = create_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO archive_snapshots "
                        "(table_name, key, value, total_chars, version, reason, created_at) "
                        "VALUES ('user_profile', '1', 'x', 1, 2, 'auto', "
                        "'2026-09-12 00:00:00.000000')"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_write())
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        row = connection.execute(
            "SELECT table_name, total_chars, version, reason FROM archive_snapshots"
        ).fetchone()
    finally:
        connection.close()
    assert row == ("user_profile", 1, 2, "auto")
