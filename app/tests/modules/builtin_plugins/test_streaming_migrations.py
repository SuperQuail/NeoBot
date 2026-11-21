"""直播插件库：v3 旧 13 位合成号群 ID → 官方 openid 迁移测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from neobot_modloader import PluginDatabase

from neobot_app.builtin_plugins.streaming_parser import db as spdb

LEGACY_GROUP = "9500000000000"
OPENID_GROUP = "9180DF39B12D4F45F9551E75800FDBC7"
ONEBOT_GROUP = "123456789"
TIMESTAMP = "2026-01-01 00:00:00"


def _v2_migrations() -> tuple[Any, ...]:
    return tuple(item for item in spdb.MIGRATIONS if item.version <= 2)


def _v2_database() -> PluginDatabase:
    return PluginDatabase(
        "streaming_parser",
        spdb.DATABASE_NAME,
        filename=spdb.DATABASE_FILENAME,
        metadata=spdb.Base.metadata,
        migrations=_v2_migrations(),
    )


def _full_database() -> PluginDatabase:
    return PluginDatabase(
        "streaming_parser",
        spdb.DATABASE_NAME,
        filename=spdb.DATABASE_FILENAME,
        metadata=spdb.Base.metadata,
        migrations=spdb.MIGRATIONS,
    )


def _write_identities(data_dir: Path) -> None:
    target = data_dir / "qqbot" / "identities.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"groups": {OPENID_GROUP: int(LEGACY_GROUP)}}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def identity(tmp_path: Path):
    from neobot_app.user_identity import bind_user_identity

    bind_user_identity(None)
    yield tmp_path
    bind_user_identity(None)


async def _insert_v2_rows(
    session: Any,
    *,
    group_ids: tuple[str, ...],
    room_id: int,
    name: str = "直播间",
) -> None:
    for group_id in group_ids:
        await session.execute(
            text(
                "INSERT INTO subscriptions "
                "(id, group_id, platform, room_id, short_id, uid, name, avatar_url, "
                "push_live, push_live_end, created_at, updated_at) "
                "VALUES (NULL, :group_id, 'bilibili', :room_id, 0, 9, :name, '', 1, 0, :ts, :ts)"
            ),
            {"group_id": group_id, "room_id": room_id, "name": name, "ts": TIMESTAMP},
        )
        await session.execute(
            text(
                "INSERT INTO group_settings "
                "(group_id, card_style, ai_reply_live, ai_reply_live_end, "
                "default_push_live, default_push_live_end, updated_at) "
                "VALUES (:group_id, '暗色', 1, 0, 1, 0, :ts)"
            ),
            {"group_id": group_id, "ts": TIMESTAMP},
        )


async def test_v3_rewrites_legacy_group_ids(tmp_path: Path, identity: Path) -> None:
    from neobot_app.user_identity import bind_user_identity

    data_dir = identity / "data"
    _write_identities(data_dir)
    bind_user_identity(data_dir)

    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_rows(
                session,
                group_ids=(LEGACY_GROUP, ONEBOT_GROUP),
                room_id=5440,
                name="甲",
            )
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            subscriptions = {
                (row[0], row[1], row[2])
                for row in await session.execute(text("SELECT group_id, room_id, name FROM subscriptions"))
            }
            # 旧合成号换成 openid；OneBot 数字群号原样保留；其余列不丢
            assert subscriptions == {
                (OPENID_GROUP, 5440, "甲"),
                (ONEBOT_GROUP, 5440, "甲"),
            }
            settings = {
                row[0]: row[1] for row in await session.execute(text("SELECT group_id, card_style FROM group_settings"))
            }
            assert settings == {OPENID_GROUP: "暗色", ONEBOT_GROUP: "暗色"}
    finally:
        await new.close()


async def test_v3_keeps_both_rows_when_openid_row_exists(tmp_path: Path, identity: Path) -> None:
    """目标 openid 行已存在时 UPDATE OR IGNORE 跳过：不删旧行、不覆盖新行。"""
    from neobot_app.user_identity import bind_user_identity

    data_dir = identity / "data"
    _write_identities(data_dir)
    bind_user_identity(data_dir)

    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_rows(session, group_ids=(LEGACY_GROUP, OPENID_GROUP), room_id=5440)
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            groups = {row[0] for row in await session.execute(text("SELECT group_id FROM subscriptions"))}
            # 旧行与新行都在（同 room_id 会撞唯一键 → 旧行被跳过保留）
            assert groups == {LEGACY_GROUP, OPENID_GROUP}
            settings = {row[0] for row in await session.execute(text("SELECT group_id FROM group_settings"))}
            assert settings == {LEGACY_GROUP, OPENID_GROUP}
    finally:
        await new.close()


async def test_v3_without_identity_file_is_noop(tmp_path: Path, identity: Path) -> None:
    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_rows(session, group_ids=(LEGACY_GROUP,), room_id=5440)
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            assert (await session.execute(text("SELECT group_id FROM subscriptions"))).scalar_one() == LEGACY_GROUP
            assert (await session.execute(text("SELECT group_id FROM group_settings"))).scalar_one() == LEGACY_GROUP
    finally:
        await new.close()
