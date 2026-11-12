"""小游戏插件库：v2→v3 结构重建（显式列拷贝）与 v4 旧合成号→openid 迁移。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from neobot_modloader import PluginDatabase

from neobot_app.builtin_plugins import minigame
from neobot_app.builtin_plugins.minigame import migrations as mg_migrations
from neobot_app.builtin_plugins.minigame.models import Base

LEGACY_USER = "9000000000001"
LEGACY_USER_2 = "9000000000002"
LEGACY_GROUP = "9500000000000"
OPENID_USER = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
OPENID_USER_2 = "B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5"
OPENID_GROUP = "9180DF39B12D4F45F9551E75800FDBC7"
ONEBOT_QQ = "123456789"
TIMESTAMP = "2026-01-01 00:00:00"


def _v2_migrations() -> tuple[Any, ...]:
    return tuple(item for item in mg_migrations.build_migrations() if item.version <= 2)


def _v2_database() -> PluginDatabase:
    """只跑 v1+v2 的库 = 升级前的旧库（user_name 在 mg_profile 末尾）。"""
    return PluginDatabase(
        "minigame",
        "main",
        filename=mg_migrations.DATABASE_FILENAME,
        metadata=Base.metadata,
        migrations=_v2_migrations(),
    )


def _full_database() -> PluginDatabase:
    return minigame.create_database()


def _write_identities(data_dir: Path) -> None:
    target = data_dir / "qqbot" / "identities.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "users": {
                    OPENID_USER: int(LEGACY_USER),
                    OPENID_USER_2: int(LEGACY_USER_2),
                },
                "groups": {OPENID_GROUP: int(LEGACY_GROUP)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def identity(tmp_path: Path):
    from neobot_app.user_identity import bind_user_identity

    bind_user_identity(None)
    yield tmp_path
    bind_user_identity(None)


async def _insert_v2_profile(session: Any, user_id: str, *, score: int, user_name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO mg_profile "
            "(user_id, score, best_score, plays, wins, updated_at, user_name) "
            "VALUES (:user_id, :score, 22, 3, 4, :updated_at, :user_name)"
        ),
        {
            "user_id": user_id,
            "score": score,
            "updated_at": TIMESTAMP,
            "user_name": user_name,
        },
    )


async def _insert_v2_other_tables(session: Any, *, user_id: str, conversation_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO mg_bottle "
            "(sender_id, sender_name, sender_avatar, content, anonymous, created_at, "
            "picked_at, picked_by, status, meta) "
            "VALUES (:sender_id, '甲', '', '你好', 0, :ts, NULL, :picked_by, 'pooled', NULL)"
        ),
        {"sender_id": user_id, "picked_by": "", "ts": TIMESTAMP},
    )
    await session.execute(
        text("INSERT INTO mg_daily (user_id, game_id, day, plays) VALUES (:user_id, 'bottle:send', '2026-01-01', 2)"),
        {"user_id": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO mg_checkin (user_id, day, score, streak, created_at) "
            "VALUES (:user_id, '2026-01-01', 7, 3, :ts)"
        ),
        {"user_id": user_id, "ts": TIMESTAMP},
    )
    await session.execute(
        text(
            "INSERT INTO mg_fortune (user_id, day, result_key, result_text, drawn_at) "
            "VALUES (:user_id, '2026-01-01', 'great', '大吉', :ts)"
        ),
        {"user_id": user_id, "ts": TIMESTAMP},
    )
    await session.execute(
        text(
            "INSERT INTO mg_record (user_id, game_id, score, conversation_id, created_at) "
            "VALUES (:user_id, 'bottle:send', 5, :conversation_id, :ts)"
        ),
        {"user_id": user_id, "conversation_id": conversation_id, "ts": TIMESTAMP},
    )


async def _column_names(database: PluginDatabase, table: str) -> list[str]:
    async with database.session() as session:
        result = await session.execute(text(f"PRAGMA table_info({table})"))
        return [row[1] for row in result]


async def test_v3_rebuild_copies_by_name_not_position(tmp_path: Path) -> None:
    """v2 的 user_name 在末尾、v3 在第二列：重建必须按列名拷贝，字段不能串。"""
    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        # 旧库（v2 状态）的列顺序就是错位根源：user_name 在最后
        assert await _column_names(old, "mg_profile") == [
            "user_id",
            "score",
            "best_score",
            "plays",
            "wins",
            "updated_at",
            "user_name",
        ]
        async with old.transaction() as session:
            await _insert_v2_profile(session, "1001", score=11, user_name="昵称甲")
            await _insert_v2_other_tables(session, user_id="1001", conversation_id="2002")
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        # v3 新表列顺序：user_name 在第二列
        assert await _column_names(new, "mg_profile") == [
            "user_id",
            "user_name",
            "score",
            "best_score",
            "plays",
            "wins",
            "updated_at",
        ]
        async with new.session() as session:
            profile = (
                (
                    await session.execute(
                        text("SELECT user_id, user_name, score, best_score, plays, wins, updated_at FROM mg_profile")
                    )
                )
                .mappings()
                .one()
            )
            assert dict(profile) == {
                "user_id": "1001",
                "user_name": "昵称甲",
                "score": 11,
                "best_score": 22,
                "plays": 3,
                "wins": 4,
                "updated_at": TIMESTAMP,
            }
            bottle = (await session.execute(text("SELECT * FROM mg_bottle"))).mappings().one()
            assert bottle["sender_id"] == "1001"
            assert bottle["content"] == "你好"
            assert bottle["created_at"] == TIMESTAMP
            assert (await session.execute(text("SELECT plays FROM mg_daily"))).scalar_one() == 2
            checkin = (await session.execute(text("SELECT score, streak, created_at FROM mg_checkin"))).mappings().one()
            assert dict(checkin) == {"score": 7, "streak": 3, "created_at": TIMESTAMP}
            fortune = (
                (await session.execute(text("SELECT result_key, result_text, drawn_at FROM mg_fortune")))
                .mappings()
                .one()
            )
            assert dict(fortune) == {
                "result_key": "great",
                "result_text": "大吉",
                "drawn_at": TIMESTAMP,
            }
            record = (
                (
                    await session.execute(
                        text("SELECT user_id, game_id, score, conversation_id, created_at FROM mg_record")
                    )
                )
                .mappings()
                .one()
            )
            assert dict(record) == {
                "user_id": "1001",
                "game_id": "bottle:send",
                "score": 5,
                "conversation_id": "2002",
                "created_at": TIMESTAMP,
            }
    finally:
        await new.close()


async def test_v4_rewrites_legacy_ids_to_openid(tmp_path: Path, identity: Path) -> None:
    """v4 借 identities.json 把旧 13 位合成号改写成 openid（含群/用户两种会话）。"""
    from neobot_app.user_identity import bind_user_identity

    data_dir = identity / "data"
    _write_identities(data_dir)
    bind_user_identity(data_dir)

    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_profile(session, LEGACY_USER, score=11, user_name="官方用户")
            await _insert_v2_other_tables(session, user_id=LEGACY_USER, conversation_id=LEGACY_GROUP)
            await session.execute(
                text(
                    "INSERT INTO mg_record (user_id, game_id, score, conversation_id, created_at) "
                    "VALUES (:uid, 'bottle:pick', 1, :cid, :ts)"
                ),
                {"uid": LEGACY_USER_2, "cid": LEGACY_USER_2, "ts": TIMESTAMP},
            )
            await session.execute(
                text(
                    "INSERT INTO mg_profile (user_id, score, best_score, plays, wins, updated_at, user_name) "
                    "VALUES (:uid, 1, 1, 1, 1, :ts, 'OneBot 用户')"
                ),
                {"uid": ONEBOT_QQ, "ts": TIMESTAMP},
            )
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            profiles = {
                row[0]: row[1] for row in await session.execute(text("SELECT user_id, user_name FROM mg_profile"))
            }
            assert profiles == {OPENID_USER: "官方用户", ONEBOT_QQ: "OneBot 用户"}
            assert (await session.execute(text("SELECT user_id FROM mg_daily"))).scalar_one() == OPENID_USER
            assert (await session.execute(text("SELECT user_id FROM mg_checkin"))).scalar_one() == OPENID_USER
            assert (await session.execute(text("SELECT user_id FROM mg_fortune"))).scalar_one() == OPENID_USER
            bottle = (await session.execute(text("SELECT sender_id, picked_by FROM mg_bottle"))).one()
            assert tuple(bottle) == (OPENID_USER, "")
            records = sorted(
                (row[0], row[1])
                for row in await session.execute(text("SELECT user_id, conversation_id FROM mg_record"))
            )
            # 群会话走 group 映射，私聊会话走 user 映射
            assert records == [
                (OPENID_USER, OPENID_GROUP),
                (OPENID_USER_2, OPENID_USER_2),
            ]
    finally:
        await new.close()


async def test_v4_keeps_both_rows_when_openid_row_exists(tmp_path: Path, identity: Path) -> None:
    """目标 openid 行已存在时跳过该行：旧数据不删、新行不被覆盖。"""
    from neobot_app.user_identity import bind_user_identity

    data_dir = identity / "data"
    _write_identities(data_dir)
    bind_user_identity(data_dir)

    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_profile(session, LEGACY_USER, score=5, user_name="旧行")
            await _insert_v2_profile(session, OPENID_USER, score=9, user_name="新行")
            await session.execute(
                text(
                    "INSERT INTO mg_checkin (user_id, day, score, streak, created_at) "
                    "VALUES (:uid, '2026-01-01', 1, 1, :ts)"
                ),
                {"uid": LEGACY_USER, "ts": TIMESTAMP},
            )
            await session.execute(
                text(
                    "INSERT INTO mg_checkin (user_id, day, score, streak, created_at) "
                    "VALUES (:uid, '2026-01-01', 2, 2, :ts)"
                ),
                {"uid": OPENID_USER, "ts": TIMESTAMP},
            )
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            profiles = {row[0]: row[1] for row in await session.execute(text("SELECT user_id, score FROM mg_profile"))}
            assert profiles == {LEGACY_USER: 5, OPENID_USER: 9}
            checkins = {row[0]: row[1] for row in await session.execute(text("SELECT user_id, score FROM mg_checkin"))}
            assert checkins == {LEGACY_USER: 1, OPENID_USER: 2}
    finally:
        await new.close()


async def test_v4_without_identity_file_is_noop(tmp_path: Path, identity: Path) -> None:
    """没有 identities.json 时旧 ID 原样保留（不阻塞启动）。"""
    databases_dir = tmp_path / "databases"
    old = _v2_database()
    await old.bind(databases_dir)
    try:
        async with old.transaction() as session:
            await _insert_v2_profile(session, LEGACY_USER, score=5, user_name="旧行")
    finally:
        await old.close()

    new = _full_database()
    await new.bind(databases_dir)
    try:
        async with new.session() as session:
            assert (await session.execute(text("SELECT user_id FROM mg_profile"))).scalar_one() == LEGACY_USER
    finally:
        await new.close()
