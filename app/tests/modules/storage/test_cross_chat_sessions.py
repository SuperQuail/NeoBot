"""跨聊天会话表：迁移 0030 往返 + 仓库按聊天流/启动标识查询。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio

from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _columns(db: Path) -> set[str]:
    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute("PRAGMA table_info(cross_chat_sessions)").fetchall()
    finally:
        connection.close()
    return {str(row[1]) for row in rows}


def test_migration_0030_round_trip(tmp_path: Path) -> None:
    """0029 → head 建表；downgrade 只删表，可往返。"""
    from alembic import command

    from neobot_storage.engine import sqlite_url

    db = tmp_path / "cross_chat_0030.db"
    cfg = _alembic_config(sqlite_url(db))

    command.upgrade(cfg, "0029")
    assert _columns(db) == set()

    command.upgrade(cfg, "head")
    # 全等，不是子集：少列/多列都要在测试里暴露
    assert _columns(db) == {
        "id", "origin_kind", "origin_id", "target_kind", "target_id",
        "task_id", "mode", "notification_mode", "status", "reply", "boot_id",
        "created_at", "updated_at",
    }

    connection = sqlite3.connect(str(db))
    try:
        connection.execute(
            "INSERT INTO cross_chat_sessions "
            "(origin_kind, origin_id, target_kind, target_id, task_id, mode, "
            " notification_mode, status, reply, boot_id, created_at, updated_at) "
            "VALUES ('group', '111', 'private', '222', 't1', 'wait', 'response', "
            "        'responded', 'hi', 'boot-a', '2026-11-07 00:00:00', '2026-11-07 00:00:00')"
        )
        connection.commit()
        kept = connection.execute(
            "SELECT origin_id, target_id, reply FROM cross_chat_sessions"
        ).fetchone()
    finally:
        connection.close()
    assert kept == ("111", "222", "hi")

    command.downgrade(cfg, "0029")
    assert _columns(db) == set()
    command.upgrade(cfg, "head")
    assert "boot_id" in _columns(db)


@pytest_asyncio.fixture
async def uow_factory():
    engine = create_memory_engine()
    await create_schema(engine)
    yield make_uow_factory(engine)
    await engine.dispose()


async def test_upsert_and_list_scoped_by_boot_id(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.cross_chat_sessions.upsert(
            origin_kind="group", origin_id="111",
            target_kind="private", target_id="222",
            task_id="t1", mode="wait", notification_mode="response",
            status="waiting", boot_id="boot-a",
        )
        await uow.cross_chat_sessions.upsert(
            origin_kind="group", origin_id="333",
            target_kind="group", target_id="444",
            task_id="t2", mode="fire_and_forget", notification_mode="no_response",
            status="delivered", boot_id="boot-b",
        )
        await uow.commit()

    async with uow_factory() as uow:
        first = await uow.cross_chat_sessions.list_for_chat(
            kind="group", conversation_id="111", boot_id="boot-a"
        )
        other_boot = await uow.cross_chat_sessions.list_for_chat(
            kind="group", conversation_id="111", boot_id="boot-b"
        )
        # 目标聊天流也能看到同一条记录
        as_target = await uow.cross_chat_sessions.list_for_chat(
            kind="private", conversation_id="222", boot_id="boot-a"
        )

    assert [item.task_id for item in first] == ["t1"]
    assert other_boot == []
    assert [item.task_id for item in as_target] == ["t1"]


async def test_record_result_updates_reply(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.cross_chat_sessions.upsert(
            origin_kind="group", origin_id="111",
            target_kind="private", target_id="222",
            task_id="t1", mode="wait", notification_mode="response",
            status="waiting", boot_id="boot-a",
        )
        updated = await uow.cross_chat_sessions.record_result(
            origin_kind="group", origin_id="111",
            target_kind="private", target_id="222",
            reply="收到", status="responded", boot_id="boot-a",
        )
        await uow.commit()

    assert updated is not None
    async with uow_factory() as uow:
        record = await uow.cross_chat_sessions.get(
            origin_kind="group", origin_id="111",
            target_kind="private", target_id="222", boot_id="boot-a",
        )
    assert record is not None
    assert record.reply == "收到"
    assert record.status == "responded"


def _unique_index_columns(db: Path) -> list[list[str]]:
    connection = sqlite3.connect(str(db))
    try:
        indexes = connection.execute("PRAGMA index_list(cross_chat_sessions)").fetchall()
        result = []
        for row in indexes:
            if not row[2]:  # unique?
                continue
            name = row[1]
            cols = [info[2] for info in connection.execute(f"PRAGMA index_info('{name}')")]
            result.append(list(cols))
    finally:
        connection.close()
    return result


def test_migration_0031_moves_boot_id_into_unique_key(tmp_path: Path) -> None:
    """0030 的唯一键是四列；0031 起是五列（含 boot_id），且可往返。"""
    from alembic import command

    from neobot_storage.engine import sqlite_url

    db = tmp_path / "cross_chat_0031.db"
    cfg = _alembic_config(sqlite_url(db))

    command.upgrade(cfg, "0030")
    before = _unique_index_columns(db)
    assert ["origin_kind", "origin_id", "target_kind", "target_id"] in before

    command.upgrade(cfg, "0031")
    after = _unique_index_columns(db)
    assert [
        "origin_kind", "origin_id", "target_kind", "target_id", "boot_id"
    ] in after
    assert _columns(db) == {
        "id", "origin_kind", "origin_id", "target_kind", "target_id",
        "task_id", "mode", "notification_mode", "status", "reply", "boot_id",
        "created_at", "updated_at",
    }

    command.downgrade(cfg, "0030")
    assert ["origin_kind", "origin_id", "target_kind", "target_id"] in _unique_index_columns(db)


@pytest.mark.asyncio
async def test_orm_and_migration_schema_match(tmp_path: Path) -> None:
    """create_all 与迁移产出的列与非空约束必须一致（含 server_default）。"""
    from alembic import command
    from sqlalchemy import inspect

    from neobot_storage.engine import create_engine, sqlite_url
    from neobot_storage.models import Base

    migrated = tmp_path / "migrated.db"
    command.upgrade(_alembic_config(sqlite_url(migrated)), "head")

    orm_engine = create_engine(sqlite_url(tmp_path / "orm.db"))
    try:
        async with orm_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with orm_engine.connect() as conn:
            orm_columns = await conn.run_sync(
                lambda sync_conn: {
                    col["name"]: (col["nullable"], str(col.get("default") or ""))
                    for col in inspect(sync_conn).get_columns("cross_chat_sessions")
                }
            )
    finally:
        await orm_engine.dispose()

    connection = sqlite3.connect(str(migrated))
    try:
        rows = connection.execute("PRAGMA table_info(cross_chat_sessions)").fetchall()
    finally:
        connection.close()
    migrated_columns = {
        str(row[1]): (not bool(row[3]), str(row[4] or "")) for row in rows
    }

    assert orm_columns == migrated_columns


async def test_repeat_upsert_resets_reply(uow_factory) -> None:
    """同一对聊天流第二次投递必须清掉上一次的回传，而不是沿用。"""
    async with uow_factory() as uow:
        await uow.cross_chat_sessions.upsert(
            origin_kind="group", origin_id="1",
            target_kind="private", target_id="2",
            task_id="t1", mode="wait", notification_mode="response",
            status="responded", boot_id="boot-a",
        )
        await uow.cross_chat_sessions.record_result(
            origin_kind="group", origin_id="1",
            target_kind="private", target_id="2",
            reply="旧回复", status="responded", boot_id="boot-a",
        )
        await uow.commit()

    async with uow_factory() as uow:
        record = await uow.cross_chat_sessions.upsert(
            origin_kind="group", origin_id="1",
            target_kind="private", target_id="2",
            task_id="t2", mode="wait", notification_mode="response",
            status="waiting", boot_id="boot-a",
        )
        await uow.commit()

    assert record.task_id == "t2"
    assert record.reply == ""
    assert record.status == "waiting"


async def test_new_boot_does_not_hide_previous_boot_rows(uow_factory) -> None:
    """两个进程重叠时，新进程写同一对不能把旧进程的行抢走。"""
    for boot in ("boot-a", "boot-b"):
        async with uow_factory() as uow:
            await uow.cross_chat_sessions.upsert(
                origin_kind="group", origin_id="1",
                target_kind="private", target_id="2",
                task_id=f"t-{boot}", mode="wait", notification_mode="response",
                status="delivered", boot_id=boot,
            )
            await uow.commit()

    async with uow_factory() as uow:
        a = await uow.cross_chat_sessions.list_for_chat(
            kind="group", conversation_id="1", boot_id="boot-a"
        )
        b = await uow.cross_chat_sessions.list_for_chat(
            kind="group", conversation_id="1", boot_id="boot-b"
        )

    assert [item.task_id for item in a] == ["t-boot-a"]
    assert [item.task_id for item in b] == ["t-boot-b"]
