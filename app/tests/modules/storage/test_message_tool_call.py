"""messages.tool_call_json：仓库往返、NULL/坏 JSON 兼容与迁移 0032 往返。

仓库用例用共享内存 SQLite（不碰 tmp_path，也不碰运行中实例的数据库）；迁移
用例需要真实文件，用系统临时目录下的普通目录——本机受限沙箱创建 0o700 目录后
无法再往里写，pytest 的 tmp_path 会失败。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import select

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_storage.models import MessageData
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema

_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
_CONV = ConversationRef(kind="group", id="g-tool-call")
_TOOL_CALL = {
    "name": "send_reply",
    "arguments": {"text": "中文内容", "segments": 2},
    "result": {"ok": True, "message_id": 7},
    "ok": True,
    "compact": False,
    "call_id": "call-1",
}


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[object]:
    eng = create_memory_engine()
    await create_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def uow_factory(engine):
    return make_uow_factory(engine)


def _message(**overrides) -> IncomingMessage:
    values = {
        "event_id": f"e-{uuid.uuid4().hex}",
        "conversation": _CONV,
        "sender_id": "bot",
        "sender_name": "Bot",
        "text": "发送成功",
        "occurred_at": _NOW,
    }
    values.update(overrides)
    return IncomingMessage(**values)


async def _history(uow_factory) -> list[IncomingMessage]:
    async with uow_factory() as uow:
        return await uow.messages.get_history(_CONV)


# ── 仓库读写 ────────────────────────────────────────────────────────


async def test_save_message_roundtrips_tool_call(uow_factory, engine) -> None:
    """tool_call 必须原样 JSON 落库，get_history 读回同一个 dict。"""

    async with uow_factory() as uow:
        await uow.messages.save_message(_message(tool_call=_TOOL_CALL))
        await uow.commit()

    history = await _history(uow_factory)

    assert len(history) == 1
    assert history[0].tool_call == _TOOL_CALL
    # ensure_ascii=False：中文按原文落库，不转 \uXXXX
    async with engine.connect() as conn:
        raw = (await conn.execute(select(MessageData.tool_call_json))).scalars().all()
    assert raw == [json.dumps(_TOOL_CALL, ensure_ascii=False)]


async def test_recent_by_sender_roundtrips_tool_call(uow_factory) -> None:
    """启动历史补齐走的 get_recent_by_sender 同样要带回 tool_call。"""

    async with uow_factory() as uow:
        await uow.messages.save_message(_message(tool_call=_TOOL_CALL))
        await uow.commit()

    async with uow_factory() as uow:
        rows = await uow.messages.get_recent_by_sender(_CONV, "bot")

    assert [row.tool_call for row in rows] == [_TOOL_CALL]


async def test_message_without_tool_call_stores_null(uow_factory, engine) -> None:
    """没有工具调用的普通消息列必须是 NULL，读回 None。"""

    async with uow_factory() as uow:
        await uow.messages.save_message(_message())
        await uow.commit()

    async with engine.connect() as conn:
        raw = (await conn.execute(select(MessageData.tool_call_json))).scalars().all()

    assert raw == [None]
    assert (await _history(uow_factory))[0].tool_call is None


async def test_non_json_values_are_stringified(uow_factory) -> None:
    """datetime 等非 JSON 原生类型按 default=str 落库，不抛异常。"""

    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    async with uow_factory() as uow:
        await uow.messages.save_message(_message(tool_call={"name": "x", "at": moment, "ok": False}))
        await uow.commit()

    assert (await _history(uow_factory))[0].tool_call == {
        "name": "x",
        "at": str(moment),
        "ok": False,
    }


@pytest.mark.parametrize(
    "raw_value",
    ["{not-json", "[1, 2, 3]", '"just-a-string"', "42"],
    ids=["broken", "json-array", "json-string", "json-number"],
)
async def test_invalid_tool_call_json_reads_back_as_none(engine, uow_factory, raw_value: str) -> None:
    """坏 JSON / 非对象 JSON 不能被当成消息读取失败：一律降级为 None。"""

    async with engine.begin() as conn:
        await conn.execute(
            MessageData.__table__.insert().values(
                event_id=f"e-{uuid.uuid4().hex}",
                conversation_kind=_CONV.kind,
                conversation_id=_CONV.id,
                sender_id="bot",
                sender_name="Bot",
                text="坏数据",
                occurred_at=_NOW,
                tool_call_json=raw_value,
            )
        )

    history = await _history(uow_factory)

    assert len(history) == 1
    assert history[0].tool_call is None


# ── 迁移 0032 ───────────────────────────────────────────────────────


@pytest.fixture()
def migration_db() -> Iterator[Path]:
    """迁移用例的 sqlite 文件（系统临时目录 + 普通目录，避开 tmp_path 的 0700）。"""
    root = Path(tempfile.gettempdir()) / f"neobot-storage-{uuid.uuid4().hex}"
    os.mkdir(root)
    try:
        yield root / "migration.db"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _message_columns(db: Path) -> dict[str, tuple[str, int, object]]:
    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute("PRAGMA table_info(messages)").fetchall()
    finally:
        connection.close()
    return {str(row[1]): (str(row[2]).upper(), int(row[3]), row[4]) for row in rows}


def _alembic_revision(db: Path) -> str:
    connection = sqlite3.connect(str(db))
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        connection.close()
    return "" if row is None else str(row[0])


def test_migration_0032_adds_and_drops_tool_call_json(migration_db: Path) -> None:
    """0031 → head 加列（Text/可空/无默认）；downgrade 删列且旧消息不丢。"""
    from alembic import command

    from neobot_storage.engine import sqlite_url

    cfg = _alembic_config(sqlite_url(migration_db))

    command.upgrade(cfg, "0031")
    assert "tool_call_json" not in _message_columns(migration_db)
    assert _alembic_revision(migration_db) == "0031"

    connection = sqlite3.connect(str(migration_db))
    try:
        connection.execute(
            "INSERT INTO messages "
            "(event_id, conversation_kind, conversation_id, sender_id, sender_name, text, occurred_at) "
            "VALUES ('e-old', 'group', 'g1', 's1', 'S', '旧消息', '2026-11-11 12:00:00')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(cfg, "head")
    assert _message_columns(migration_db)["tool_call_json"] == ("TEXT", 0, None)
    assert _alembic_revision(migration_db) == "0032"
    connection = sqlite3.connect(str(migration_db))
    try:
        # 升级前就存在的消息列值为 NULL
        assert connection.execute("SELECT tool_call_json FROM messages").fetchone() == (None,)
    finally:
        connection.close()

    command.downgrade(cfg, "0031")
    assert "tool_call_json" not in _message_columns(migration_db)
    assert _alembic_revision(migration_db) == "0031"
    connection = sqlite3.connect(str(migration_db))
    try:
        assert connection.execute("SELECT event_id, text FROM messages").fetchall() == [("e-old", "旧消息")]
    finally:
        connection.close()

    command.upgrade(cfg, "head")
    assert _message_columns(migration_db)["tool_call_json"] == ("TEXT", 0, None)
