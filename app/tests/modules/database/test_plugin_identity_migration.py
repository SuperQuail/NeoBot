"""内置插件独立库 identity 迁移测试（旧数字 ID → openid）。

边界/门控/schema 契约/speaking_schedule 的用例在
test_plugin_identity_migration_edges.py，它复用本文件的 fixture。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from neobot_app.database.plugin_identity_migration import migrate_plugin_databases

OLD_USER = "9000000000001"
OPENID_USER = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
OLD_USER2 = "9000000000002"
OPENID_USER2 = "B1C2D3E4F5A6B1C2D3E4F5A6B1C2D3E4"
OLD_GROUP = "9500000000001"
OPENID_GROUP = "9180DF39B12D4F45F9551E75800FDBC7"
OLD_GROUP2 = "9500000000002"
OPENID_GROUP2 = "A180DF39B12D4F45F9551E75800FDBC8"
OLD_GROUP3 = "9500000000003"
OPENID_GROUP3 = "B180DF39B12D4F45F9551E75800FDBC9"
OLD_GROUP4 = "9500000000004"
OPENID_GROUP4 = "C180DF39B12D4F45F9551E75800FDBCA"
NORMAL_QQ = "123456789"

#: 与 builtin_plugins/streaming_parser/db.py 的 v3 DDL 一致（最小复刻）。
_STREAMING_PARSER_DDL = """
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id VARCHAR(64) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    room_id BIGINT NOT NULL,
    short_id BIGINT NOT NULL,
    uid BIGINT NOT NULL,
    name VARCHAR(128) NOT NULL,
    avatar_url VARCHAR(512) NOT NULL,
    push_live BOOLEAN NOT NULL,
    push_live_end BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_subscription UNIQUE (group_id, platform, room_id)
);
CREATE TABLE group_settings (
    group_id VARCHAR(64) NOT NULL PRIMARY KEY,
    card_style VARCHAR(32) NOT NULL,
    ai_reply_live BOOLEAN NOT NULL,
    ai_reply_live_end BOOLEAN NOT NULL,
    default_push_live BOOLEAN NOT NULL,
    default_push_live_end BOOLEAN NOT NULL,
    updated_at DATETIME NOT NULL
);
"""

#: 与 builtin_plugins/minigame/migrations.py 的 v3 DDL 一致（最小复刻）。
_MINIGAME_DDL = """
CREATE TABLE mg_profile (
    user_id VARCHAR(128) NOT NULL PRIMARY KEY,
    user_name VARCHAR(128) NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    best_score INTEGER NOT NULL DEFAULT 0,
    plays INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL
);
CREATE TABLE mg_bottle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id VARCHAR(128) NOT NULL DEFAULT '',
    sender_name VARCHAR(128) NOT NULL DEFAULT '',
    sender_avatar TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    anonymous BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    picked_at DATETIME,
    picked_by VARCHAR(128) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'pooled',
    meta JSON
);
CREATE TABLE mg_daily (
    user_id VARCHAR(128) NOT NULL,
    game_id VARCHAR(32) NOT NULL,
    day VARCHAR(10) NOT NULL,
    plays INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, game_id, day)
);
CREATE TABLE mg_checkin (
    user_id VARCHAR(128) NOT NULL,
    day VARCHAR(10) NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE mg_fortune (
    user_id VARCHAR(128) NOT NULL,
    day VARCHAR(10) NOT NULL,
    result_key VARCHAR(32) NOT NULL DEFAULT '',
    result_text TEXT NOT NULL DEFAULT '',
    drawn_at DATETIME NOT NULL,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE mg_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(128) NOT NULL DEFAULT '',
    game_id VARCHAR(32) NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    conversation_id VARCHAR(128) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL
);
"""

#: 与 builtin_plugins/starship/migrations.py 的 DDL 一致（最小复刻）。
_STARSHIP_DDL = """
CREATE TABLE starship_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game VARCHAR(64) NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    player VARCHAR(64) NOT NULL DEFAULT '',
    user_id VARCHAR(128) NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL
);
"""


class _RecordingLogger:
    """记录日志调用，供断言 WARNING。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def bind(self, **ctx: Any) -> "_RecordingLogger":
        return self

    def _record(self, level: str, msg: str, **kw: Any) -> None:
        self.records.append((level, msg, kw))

    def debug(self, msg: str, **kw: Any) -> None:
        self._record("debug", msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._record("info", msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._record("warning", msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._record("error", msg, **kw)

    def exception(self, msg: str, **kw: Any) -> None:
        self._record("exception", msg, **kw)


def _db(root: Path, plugin: str, filename: str) -> Path:
    return root / plugin / "databases" / filename


def _create(path: Path, ddl: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(ddl)


def _scalar(path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(path) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def _rows(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(sql, params).fetchall()


def _backups(path: Path, table: str | None = None) -> list[tuple[Any, ...]]:
    sql = "SELECT run_at, table_name, old_key, new_key, payload FROM identity_migration_backup"
    params: tuple[Any, ...] = ()
    if table:
        sql += " WHERE table_name=?"
        params = (table,)
    return _rows(path, sql + " ORDER BY id", params)


def _has_table(path: Path, table: str) -> bool:
    return _scalar(path, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)) == 1


def _assert_backup_table_exists(path: Path) -> None:
    assert _has_table(path, "identity_migration_backup")


def _seed_streaming_parser(root: Path) -> Path:
    db = _db(root, "streaming_parser", "streaming_parser.db")
    _create(db, _STREAMING_PARSER_DDL)
    with sqlite3.connect(db) as conn:
        sub = (
            "INSERT INTO subscriptions (group_id, platform, room_id, short_id, uid, name, "
            "avatar_url, push_live, push_live_end, created_at, updated_at) "
            "VALUES (?, 'bilibili', ?, 0, 0, ?, '', 1, 0, '2026-01-01 00:00:00', "
            "'2026-01-01 00:00:00')"
        )
        conn.execute(sub, (OLD_GROUP, 100, "旧-100"))
        # 目标群已订阅同一 platform+room → 冲突，旧行留档后删
        conn.execute(sub, (OLD_GROUP, 200, "旧-200"))
        conn.execute(sub, (OPENID_GROUP, 200, "目标-200"))
        conn.execute(sub, (NORMAL_QQ, 300, "普通"))
        setting = (
            "INSERT INTO group_settings (group_id, card_style, ai_reply_live, "
            "ai_reply_live_end, default_push_live, default_push_live_end, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        # 目标 card_style 非空 → 目标优先；布尔 OR
        conn.execute(setting, (OLD_GROUP2, "", 0, 1, 0, 1, "2026-01-01 00:00:00"))
        conn.execute(setting, (OPENID_GROUP2, "blue", 1, 0, 0, 0, "2026-02-01 00:00:00"))
        # 目标 card_style 为空 → 回退旧值；updated_at 取新
        conn.execute(setting, (OLD_GROUP3, "pink", 1, 0, 1, 0, "2026-03-01 00:00:00"))
        conn.execute(setting, (OPENID_GROUP3, "", 0, 0, 1, 0, "2026-01-15 00:00:00"))
        # 目标不存在 → 直接改主键
        conn.execute(setting, (OLD_GROUP4, "green", 1, 0, 1, 0, "2026-04-01 00:00:00"))
    return db


def _seed_minigame(root: Path) -> Path:
    db = _db(root, "minigame", "minigame.db")
    _create(db, _MINIGAME_DDL)
    with sqlite3.connect(db) as conn:
        profile = (
            "INSERT INTO mg_profile (user_id, user_name, score, best_score, plays, wins, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        conn.execute(profile, (OLD_USER, "", 10, 20, 2, 1, "2026-01-01 00:00:00"))
        conn.execute(profile, (OPENID_USER, "新名字", 5, 30, 3, 2, "2026-02-01 00:00:00"))
        conn.execute(profile, (OLD_USER2, "旧二", 7, 8, 1, 0, "2026-01-05 00:00:00"))

        conn.execute("INSERT INTO mg_daily VALUES (?, ?, ?, ?)", (OLD_USER, "g1", "2026-01-01", 3))
        conn.execute("INSERT INTO mg_daily VALUES (?, ?, ?, ?)", (OPENID_USER, "g1", "2026-01-01", 4))
        conn.execute("INSERT INTO mg_daily VALUES (?, ?, ?, ?)", (OLD_USER, "g2", "2026-01-01", 2))

        conn.execute(
            "INSERT INTO mg_checkin VALUES (?, ?, ?, ?, ?)",
            (OLD_USER, "2026-01-01", 5, 2, "2026-01-01 08:00:00"),
        )
        conn.execute(
            "INSERT INTO mg_checkin VALUES (?, ?, ?, ?, ?)",
            (OPENID_USER, "2026-01-01", 10, 1, "2026-01-02 08:00:00"),
        )
        conn.execute(
            "INSERT INTO mg_checkin VALUES (?, ?, ?, ?, ?)",
            (OLD_USER2, "2026-01-02", 1, 1, "2026-01-02 09:00:00"),
        )

        conn.execute(
            "INSERT INTO mg_fortune (user_id, day, result_key, result_text, drawn_at) VALUES (?, ?, ?, ?, ?)",
            (OLD_USER, "2026-01-01", "old_key", "旧签", "2026-01-01 07:00:00"),
        )
        conn.execute(
            "INSERT INTO mg_fortune (user_id, day, result_key, result_text, drawn_at) VALUES (?, ?, ?, ?, ?)",
            (OPENID_USER, "2026-01-01", "new_key", "新签", "2026-01-01 09:00:00"),
        )
        conn.execute(
            "INSERT INTO mg_fortune (user_id, day, result_key, result_text, drawn_at) VALUES (?, ?, ?, ?, ?)",
            (OLD_USER2, "2026-01-03", "k2", "二签", "2026-01-03 09:00:00"),
        )

        bottle = (
            "INSERT INTO mg_bottle (sender_id, sender_name, content, created_at, picked_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        conn.execute(bottle, (OLD_USER, "甲", "瓶1", "2026-01-01 00:00:00", OLD_USER2, "picked"))
        conn.execute(bottle, (OLD_USER2, "乙", "瓶2", "2026-01-01 00:00:00", "", "pooled"))

        record = "INSERT INTO mg_record (user_id, game_id, score, conversation_id, created_at) VALUES (?, ?, ?, ?, ?)"
        conn.execute(record, (OLD_USER, "g1", 3, OLD_GROUP, "2026-01-01 00:00:00"))
        conn.execute(record, (OLD_USER2, "g1", 4, OLD_USER, "2026-01-01 00:00:00"))
    return db


def _seed_starship(root: Path) -> Path:
    db = _db(root, "starship", "starship.db")
    _create(db, _STARSHIP_DDL)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO starship_scores (game, score, user_id, player, created_at) "
            "VALUES ('xj', 9, ?, '旧玩家', '2026-01-01 00:00:00')",
            (OLD_USER,),
        )
        conn.execute(
            "INSERT INTO starship_scores (game, score, user_id, player, created_at) "
            "VALUES ('xj', 5, ?, '普通人', '2026-01-01 00:00:00')",
            (NORMAL_QQ,),
        )
    return db


def test_streaming_parser_migration(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _seed_streaming_parser(root)
    group_map = {
        OLD_GROUP: OPENID_GROUP,
        OLD_GROUP2: OPENID_GROUP2,
        OLD_GROUP3: OPENID_GROUP3,
        OLD_GROUP4: OPENID_GROUP4,
    }
    log = _RecordingLogger()

    result = migrate_plugin_databases(root, user_map={}, group_map=group_map, official_only=True, logger=log)

    assert result == {"streaming_parser": {"subscriptions": 2, "group_settings": 3}}
    # 订阅：无冲突直接改；有冲突删旧行、目标行保留
    subs = _rows(db, "SELECT group_id, room_id, name FROM subscriptions ORDER BY room_id")
    assert subs == [
        (OPENID_GROUP, 100, "旧-100"),
        (OPENID_GROUP, 200, "目标-200"),
        (NORMAL_QQ, 300, "普通"),
    ]
    # 群设置：目标非空优先 / 空则回退旧值 / 布尔 OR / updated_at 取新
    merged = _rows(
        db,
        "SELECT group_id, card_style, ai_reply_live, ai_reply_live_end, "
        "default_push_live, default_push_live_end, updated_at FROM group_settings "
        "WHERE group_id IN (?, ?, ?) ORDER BY group_id",
        (OPENID_GROUP2, OPENID_GROUP3, OPENID_GROUP4),
    )
    assert merged == [
        (OPENID_GROUP2, "blue", 1, 1, 0, 1, "2026-02-01 00:00:00"),
        (OPENID_GROUP3, "pink", 1, 0, 1, 0, "2026-03-01 00:00:00"),
        (OPENID_GROUP4, "green", 1, 0, 1, 0, "2026-04-01 00:00:00"),
    ]
    assert _scalar(db, "SELECT COUNT(*) FROM group_settings WHERE group_id LIKE '95%'") == 0
    # 备份：订阅冲突 1 行 + 两条合并旧行
    _assert_backup_table_exists(db)
    backups = _backups(db)
    assert len(backups) == 3
    assert all(run_at for run_at, *_rest in backups)
    sub_payload = [json.loads(payload) for _run_at, table, _old, _new, payload in backups if table == "subscriptions"]
    assert [(p["group_id"], p["room_id"], p["name"]) for p in sub_payload] == [(OLD_GROUP, 200, "旧-200")]
    settings_payload = {
        _old: json.loads(payload) for _run_at, table, _old, _new, payload in backups if table == "group_settings"
    }
    assert settings_payload[OLD_GROUP2]["card_style"] == ""
    assert settings_payload[OLD_GROUP2]["ai_reply_live_end"] == 1
    # 迁移成功只记一条 INFO，无 WARNING
    assert [r for r in log.records if r[0] != "info"] == []
    assert len([r for r in log.records if r[0] == "info"]) == 1


def test_minigame_migration(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _seed_minigame(root)
    user_map = {OLD_USER: OPENID_USER, OLD_USER2: OPENID_USER2}
    group_map = {OLD_GROUP: OPENID_GROUP}

    result = migrate_plugin_databases(root, user_map=user_map, group_map=group_map, official_only=True)

    assert result == {
        "minigame": {
            "mg_profile": 2,
            "mg_daily": 2,
            "mg_checkin": 2,
            "mg_fortune": 2,
            "mg_bottle": 3,
            "mg_record": 4,
        }
    }
    # 档案：分数相加、最高分取大、场次/胜场相加、昵称目标非空优先、updated_at 取新
    assert _rows(
        db,
        "SELECT user_id, user_name, score, best_score, plays, wins, updated_at FROM mg_profile ORDER BY user_id",
    ) == [
        (OPENID_USER, "新名字", 15, 30, 5, 3, "2026-02-01 00:00:00"),
        (OPENID_USER2, "旧二", 7, 8, 1, 0, "2026-01-05 00:00:00"),
    ]
    # 每日场次：冲突相加，非冲突改 user_id
    assert _rows(db, "SELECT user_id, game_id, plays FROM mg_daily ORDER BY game_id, day") == [
        (OPENID_USER, "g1", 7),
        (OPENID_USER, "g2", 2),
    ]
    # 签到：积分相加、streak 取大、created_at 取早
    assert _rows(db, "SELECT user_id, day, score, streak, created_at FROM mg_checkin ORDER BY day") == [
        (OPENID_USER, "2026-01-01", 15, 2, "2026-01-01 08:00:00"),
        (OPENID_USER2, "2026-01-02", 1, 1, "2026-01-02 09:00:00"),
    ]
    # 运势：冲突保留目标
    assert _rows(db, "SELECT user_id, day, result_key FROM mg_fortune ORDER BY day") == [
        (OPENID_USER, "2026-01-01", "new_key"),
        (OPENID_USER2, "2026-01-03", "k2"),
    ]
    # 漂流瓶 sender_id / picked_by 直接改
    assert _rows(db, "SELECT sender_id, picked_by, content FROM mg_bottle ORDER BY id") == [
        (OPENID_USER, OPENID_USER2, "瓶1"),
        (OPENID_USER2, "", "瓶2"),
    ]
    # 记录：user_id 改用户；conversation_id 群/用户两种映射
    assert _rows(db, "SELECT user_id, conversation_id FROM mg_record ORDER BY id") == [
        (OPENID_USER, OPENID_GROUP),
        (OPENID_USER2, OPENID_USER),
    ]
    # 备份：4 条合并/删除的旧行，覆盖四张有主键冲突的表
    _assert_backup_table_exists(db)
    backups = _backups(db)
    assert len(backups) == 4
    assert {table for _run_at, table, _old, _new, payload in backups} == {
        "mg_profile",
        "mg_daily",
        "mg_checkin",
        "mg_fortune",
    }
    fortune = [b for b in backups if b[1] == "mg_fortune"][0]
    assert json.loads(fortune[4])["result_key"] == "old_key"


def test_starship_migration(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _seed_starship(root)

    result = migrate_plugin_databases(root, user_map={OLD_USER: OPENID_USER}, group_map={})

    assert result == {"starship": {"starship_scores": 1}}
    assert _rows(db, "SELECT user_id FROM starship_scores ORDER BY id") == [
        (OPENID_USER,),
        (NORMAL_QQ,),
    ]
    # 没有删除/合并也要有备份表（约定：每个处理过的库都有）
    _assert_backup_table_exists(db)
    assert _backups(db) == []


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    _seed_streaming_parser(root)
    _seed_minigame(root)
    _seed_starship(root)
    user_map = {OLD_USER: OPENID_USER, OLD_USER2: OPENID_USER2}
    group_map = {
        OLD_GROUP: OPENID_GROUP,
        OLD_GROUP2: OPENID_GROUP2,
        OLD_GROUP3: OPENID_GROUP3,
        OLD_GROUP4: OPENID_GROUP4,
    }

    first = migrate_plugin_databases(root, user_map=user_map, group_map=group_map, official_only=True)
    assert set(first) == {"streaming_parser", "minigame", "starship"}
    minigame_db = _db(root, "minigame", "minigame.db")
    before = (
        _rows(minigame_db, "SELECT * FROM mg_profile ORDER BY user_id"),
        _rows(minigame_db, "SELECT * FROM mg_daily ORDER BY user_id, game_id"),
        _rows(minigame_db, "SELECT * FROM mg_checkin ORDER BY user_id, day"),
        len(_backups(minigame_db)),
    )

    log = _RecordingLogger()
    second = migrate_plugin_databases(root, user_map=user_map, group_map=group_map, official_only=True, logger=log)

    assert second == {}
    assert (
        _rows(minigame_db, "SELECT * FROM mg_profile ORDER BY user_id"),
        _rows(minigame_db, "SELECT * FROM mg_daily ORDER BY user_id, game_id"),
        _rows(minigame_db, "SELECT * FROM mg_checkin ORDER BY user_id, day"),
        len(_backups(minigame_db)),
    ) == before
    assert log.records == [], "无迁移时不得再刷日志"


def test_missing_databases_are_noop(tmp_path: Path) -> None:
    log = _RecordingLogger()
    assert migrate_plugin_databases(tmp_path / "plugins_data", user_map={OLD_USER: OPENID_USER}, group_map={}) == {}
    assert log.records == []


def test_empty_mapping_is_noop(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _seed_starship(root)
    log = _RecordingLogger()

    assert migrate_plugin_databases(root, user_map={}, group_map={}, logger=log) == {}
    assert _rows(db, "SELECT user_id FROM starship_scores ORDER BY id") == [
        (OLD_USER,),
        (NORMAL_QQ,),
    ]
    assert log.records == []
