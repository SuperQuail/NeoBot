"""用户头像存储：迁移 0027 往返 + user_data 三列的仓库读写（spec(5) §4.9）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from neobot_contracts.time_context import now_utc
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema

AVATAR_COLUMNS = {"avatar_path", "avatar_fetched_at", "avatar_fail_count"}


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _columns(db: Path, table: str) -> set[str]:
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        connection.close()
    return {str(row[1]) for row in rows}


def test_migration_0027_round_trip(tmp_path: Path) -> None:
    """A36：0027 upgrade / downgrade 往返正常，三列随迁移出现与消失。"""
    import sqlite3

    from alembic import command

    from neobot_storage.engine import sqlite_url

    db = tmp_path / "avatars.db"
    cfg = _alembic_config(sqlite_url(db))

    command.upgrade(cfg, "0026")
    assert AVATAR_COLUMNS & _columns(db, "user_data") == set()

    command.upgrade(cfg, "head")
    assert AVATAR_COLUMNS <= _columns(db, "user_data")

    # 三列的约束：路径 / 时间可空，失败次数非空且默认 0（既有行与新行都拿到 0）
    info = {row[1]: row for row in sqlite3.connect(str(db)).execute("PRAGMA table_info(user_data)")}
    assert info["avatar_path"][3] == 0, "avatar_path 必须可空"
    assert info["avatar_fetched_at"][3] == 0, "avatar_fetched_at 必须可空"
    assert info["avatar_fail_count"][3] == 1, "avatar_fail_count 必须非空"
    # PRAGMA 的 dflt_value 是 SQL 字面量文本（可能是 '0'）',
    assert "0" in str(info["avatar_fail_count"][4]), "avatar_fail_count 默认 0"

    connection = sqlite3.connect(str(db))
    try:
        connection.execute("INSERT INTO user_data (user_id, nick_name) VALUES ('10001', 'tester')")
        connection.commit()
        row = connection.execute(
            "SELECT avatar_path, avatar_fetched_at, avatar_fail_count "
            "FROM user_data WHERE user_id = '10001'"
        ).fetchone()
    finally:
        connection.close()
    assert row == (None, None, 0)

    # 往返：downgrade 只移除三列，既有用户资料行不受影响
    command.downgrade(cfg, "0026")
    assert AVATAR_COLUMNS & _columns(db, "user_data") == set()
    connection = sqlite3.connect(str(db))
    try:
        kept = connection.execute(
            "SELECT nick_name FROM user_data WHERE user_id = '10001'"
        ).fetchone()
    finally:
        connection.close()
    assert kept == ("tester",)

    command.upgrade(cfg, "head")
    assert AVATAR_COLUMNS <= _columns(db, "user_data")


@pytest_asyncio.fixture
async def uow_factory():
    engine = create_memory_engine()
    await create_schema(engine)
    yield make_uow_factory(engine)
    await engine.dispose()


async def test_upsert_user_writes_all_three_avatar_columns(uow_factory) -> None:
    fetched_at = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    async with uow_factory() as uow:
        await uow.profiles.upsert_user(
            "10001",
            avatar_path="/data/avatars/10001.png",
            avatar_fetched_at=fetched_at,
            avatar_fail_count=0,
        )
        await uow.commit()

    async with uow_factory() as uow:
        row = await uow.profiles.get_user("10001")
    assert row is not None
    assert row.avatar_path == "/data/avatars/10001.png"
    assert row.avatar_fail_count == 0
    assert row.avatar_fetched_at is not None


async def test_bump_avatar_fail_count_creates_row_and_never_touches_avatar(uow_factory) -> None:
    """失败计数是原子自增；失败不得覆盖 avatar_path / avatar_fetched_at。"""
    fetched_at = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    async with uow_factory() as uow:
        await uow.profiles.upsert_user(
            "10002",
            avatar_path="/data/avatars/10002.png",
            avatar_fetched_at=fetched_at,
            avatar_fail_count=0,
        )
        await uow.commit()

    for expected in (1, 2, 3):
        async with uow_factory() as uow:
            await uow.profiles.bump_avatar_fail_count("10002")
            await uow.commit()
        async with uow_factory() as uow:
            row = await uow.profiles.get_user("10002")
        assert row is not None
        assert row.avatar_fail_count == expected
        assert row.avatar_path == "/data/avatars/10002.png"
        assert row.avatar_fetched_at is not None

    # 行不存在时建行（失败也要留下可诊断的痕迹）
    async with uow_factory() as uow:
        await uow.profiles.bump_avatar_fail_count("19999")
        await uow.commit()
    async with uow_factory() as uow:
        row = await uow.profiles.get_user("19999")
    assert row is not None
    assert row.avatar_fail_count == 1
    assert row.avatar_path is None


async def test_clear_avatar_keeps_user_row(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.profiles.upsert_user(
            "10003",
            nick_name="tester",
            avatar_path="/data/avatars/10003.png",
            avatar_fetched_at=now_utc(),
            avatar_fail_count=2,
        )
        await uow.commit()

    async with uow_factory() as uow:
        await uow.profiles.clear_avatar("10003")
        await uow.commit()
    async with uow_factory() as uow:
        row = await uow.profiles.get_user("10003")
    # 「有 user_data 行 = 认识该用户」：清空头像不等于忘记这个人
    assert row is not None
    assert row.nick_name == "tester"
    assert row.avatar_path is None and row.avatar_fetched_at is None
    assert row.avatar_fail_count == 0


async def test_list_stale_avatars_filters_sorts_and_limits(uow_factory) -> None:
    now = now_utc()
    async with uow_factory() as uow:
        await uow.profiles.upsert_user(
            "old",
            avatar_path="/a/old.png",
            avatar_fetched_at=now - timedelta(days=120),
        )
        await uow.profiles.upsert_user(
            "older",
            avatar_path="/a/older.png",
            avatar_fetched_at=now - timedelta(days=200),
        )
        await uow.profiles.upsert_user(
            "fresh",
            avatar_path="/a/fresh.png",
            avatar_fetched_at=now - timedelta(days=1),
        )
        await uow.profiles.upsert_user("no_avatar", nick_name="only profile")
        await uow.commit()

    cutoff = now - timedelta(days=90)
    async with uow_factory() as uow:
        rows = await uow.profiles.list_stale_avatars(cutoff)
    assert [row.user_id for row in rows] == ["older", "old"]

    async with uow_factory() as uow:
        limited = await uow.profiles.list_stale_avatars(cutoff, limit=1)
    assert [row.user_id for row in limited] == ["older"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
