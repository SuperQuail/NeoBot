"""插件 identity 迁移的边界/门控/schema 契约/speaking_schedule 测试。

复用 test_plugin_identity_migration.py 的 fixture（最小 schema、种子库），避免两份
schema 漂移；本文件只放边界与契约用例，保持单文件 < PR 门禁 500 行。
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

import pytest

from neobot_app.database.plugin_identity_migration import _DATABASES, _MIGRATORS
from neobot_app.database.plugin_identity_migration import migrate_plugin_databases
from tests.modules.database.test_plugin_identity_migration import (
    NORMAL_QQ,
    OLD_GROUP,
    OLD_GROUP2,
    OLD_USER,
    OLD_USER2,
    OPENID_GROUP,
    OPENID_GROUP2,
    OPENID_USER,
    OPENID_USER2,
    _MINIGAME_DDL,
    _STREAMING_PARSER_DDL,
    _RecordingLogger,
    _backups,
    _create,
    _db,
    _has_table,
    _rows,
    _scalar,
    _seed_minigame,
    _seed_streaming_parser,
    _seed_starship,
)

#: 释放版（#305 之前）streaming_parser v1 的表结构：group_id 是 BIGINT。
#: 升级先跑本迁移、再跑插件自己的 v2/v3 重建，所以要验证整数列的亲和性不影响改写。
_V1_STREAMING_PARSER_DDL = """
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id BIGINT NOT NULL,
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
    group_id BIGINT NOT NULL PRIMARY KEY,
    card_style VARCHAR(32) NOT NULL,
    ai_reply_live BOOLEAN NOT NULL,
    ai_reply_live_end BOOLEAN NOT NULL,
    default_push_live BOOLEAN NOT NULL,
    default_push_live_end BOOLEAN NOT NULL,
    updated_at DATETIME NOT NULL
);
"""


def _seed_speaking_schedule(
    root: Path,
    overrides: list[tuple[str, str]],
    mutes: dict[str, Any] | None = None,
) -> Path:
    """造 speaking_schedule 的 config.toml / mutes.json（真实格式见插件 runtime/state）。"""
    directory = root / "speaking_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    lines = ['timezone = "Asia/Shanghai"', ""]
    for kind, local in overrides:
        lines += ["[[overrides]]", f'kind = "{kind}"', f'id = "{local}"', ""]
    (directory / "config.toml").write_text("\n".join(lines), encoding="utf-8")
    if mutes is not None:
        (directory / "mutes.json").write_text(json.dumps(mutes, ensure_ascii=False), encoding="utf-8")
    return directory


def _config_overrides(root: Path) -> list[tuple[str, str]]:
    data = tomllib.loads((root / "speaking_schedule" / "config.toml").read_text(encoding="utf-8"))
    return [(item["kind"], item["id"]) for item in data.get("overrides", [])]


def _identity_backups(directory: Path, filename: str) -> list[Path]:
    return sorted(directory.glob(f"{filename}.identity-backup-*"))


def test_v1_integer_group_id_schema(tmp_path: Path) -> None:
    """释放版 streaming_parser 还是 v1（group_id BIGINT），升级时先跑本迁移。"""
    root = tmp_path / "plugins_data"
    db = _db(root, "streaming_parser", "streaming_parser.db")
    _create(db, _V1_STREAMING_PARSER_DDL)
    with sqlite3.connect(db) as conn:
        sub = (
            "INSERT INTO subscriptions (group_id, platform, room_id, short_id, uid, name, "
            "avatar_url, push_live, push_live_end, created_at, updated_at) "
            "VALUES (?, 'bilibili', ?, 0, 0, ?, '', 1, 0, '2026-01-01 00:00:00', "
            "'2026-01-01 00:00:00')"
        )
        conn.execute(sub, (int(OLD_GROUP), 100, "旧-100"))
        conn.execute(sub, (int(OLD_GROUP), 200, "旧-200"))
        conn.execute(sub, (OPENID_GROUP, 200, "目标-200"))
        conn.execute(sub, (int(NORMAL_QQ), 300, "普通"))
        setting = (
            "INSERT INTO group_settings (group_id, card_style, ai_reply_live, "
            "ai_reply_live_end, default_push_live, default_push_live_end, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        conn.execute(setting, (int(OLD_GROUP2), "", 0, 1, 0, 1, "2026-01-01 00:00:00"))
        conn.execute(setting, (OPENID_GROUP2, "blue", 1, 0, 0, 0, "2026-02-01 00:00:00"))

    result = migrate_plugin_databases(
        root,
        user_map={},
        group_map={OLD_GROUP: OPENID_GROUP, OLD_GROUP2: OPENID_GROUP2},
        official_only=True,
    )

    assert result == {"streaming_parser": {"subscriptions": 2, "group_settings": 1}}
    # 整数列写入 openid 后按 TEXT 存（SQLite 亲和性），旧整数群号已不在
    assert _rows(db, "SELECT typeof(group_id), group_id, room_id FROM subscriptions ORDER BY room_id") == [
        ("text", OPENID_GROUP, 100),
        ("text", OPENID_GROUP, 200),
        ("integer", int(NORMAL_QQ), 300),
    ]
    merged = _rows(
        db,
        "SELECT typeof(group_id), group_id, card_style, ai_reply_live, ai_reply_live_end, "
        "updated_at FROM group_settings",
    )
    assert merged == [
        ("text", OPENID_GROUP2, "blue", 1, 1, "2026-02-01 00:00:00"),
    ]
    assert len(_backups(db)) == 2


def test_official_only_defaults_to_false(tmp_path: Path) -> None:
    """调用方漏传 official_only 时必须 fail-closed：不动群绑定。"""
    root = tmp_path / "plugins_data"
    _seed_streaming_parser(root)
    assert migrate_plugin_databases(root, user_map={}, group_map={OLD_GROUP: OPENID_GROUP}) == {}


@pytest.mark.parametrize("mode", ["dual", "onebot"])
def test_non_official_modes_keep_group_and_conversation_bindings(tmp_path: Path, mode: str) -> None:
    """dual/OneBot 模式：群订阅、群设置、会话绑定、作息配置都保持真实数字 ID。"""
    root = tmp_path / mode / "plugins_data"
    streaming_db = _seed_streaming_parser(root)
    minigame_db = _seed_minigame(root)
    _seed_starship(root)
    with sqlite3.connect(minigame_db) as conn:
        conn.execute(
            "UPDATE mg_bottle SET meta=? WHERE id=1",
            (json.dumps({"mode": "normal", "conversation": OLD_GROUP}),),
        )
    directory = _seed_speaking_schedule(root, [("group", OLD_GROUP)])
    original_config = (directory / "config.toml").read_bytes()
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root,
        user_map={OLD_USER: OPENID_USER, OLD_USER2: OPENID_USER2},
        group_map={OLD_GROUP: OPENID_GROUP},
        official_only=False,
        logger=log,
    )

    # streaming_parser 整库跳过：旧群号原样，连备份表都不建
    assert "streaming_parser" not in result
    assert _rows(streaming_db, "SELECT group_id FROM subscriptions ORDER BY id") == [
        (OLD_GROUP,),
        (OLD_GROUP,),
        (OPENID_GROUP,),
        (NORMAL_QQ,),
    ]
    assert not _has_table(streaming_db, "identity_migration_backup")
    # minigame：用户级照迁，会话绑定（conversation_id / meta）不动
    assert result["minigame"] == {
        "mg_profile": 2,
        "mg_daily": 2,
        "mg_checkin": 2,
        "mg_fortune": 2,
        "mg_bottle": 3,
        "mg_record": 2,
    }
    assert _rows(minigame_db, "SELECT user_id, conversation_id FROM mg_record ORDER BY id") == [
        (OPENID_USER, OLD_GROUP),
        (OPENID_USER2, OLD_USER),
    ]
    assert json.loads(_scalar(minigame_db, "SELECT meta FROM mg_bottle WHERE id=1"))["conversation"] == OLD_GROUP
    # starship 用户级照迁
    assert result["starship"] == {"starship_scores": 1}
    # speaking_schedule 文件整份跳过
    assert "speaking_schedule" not in result
    assert (directory / "config.toml").read_bytes() == original_config
    assert not _identity_backups(directory, "config.toml")
    assert [r for r in log.records if r[0] == "warning"] == []


def test_subscription_conflict_merges_push_flags_and_name(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _db(root, "streaming_parser", "streaming_parser.db")
    _create(db, _STREAMING_PARSER_DDL)
    insert = (
        "INSERT INTO subscriptions (group_id, platform, room_id, short_id, uid, name, "
        "avatar_url, push_live, push_live_end, created_at, updated_at) "
        "VALUES (?, 'bilibili', ?, 0, 0, ?, '', ?, ?, '2026-01-01 00:00:00', "
        "'2026-01-01 00:00:00')"
    )
    with sqlite3.connect(db) as conn:
        # 旧行关过开播推送、开着下播推送；目标行反之 → OR 后两个都开
        conn.execute(insert, (OLD_GROUP, 100, "旧-100", 0, 1))
        conn.execute(insert, (OPENID_GROUP, 100, "目标-100", 1, 0))
        # 目标名称为空 → 回退旧名
        conn.execute(insert, (OLD_GROUP, 200, "旧名", 1, 0))
        conn.execute(insert, (OPENID_GROUP, 200, "", 0, 0))

    result = migrate_plugin_databases(root, user_map={}, group_map={OLD_GROUP: OPENID_GROUP}, official_only=True)

    assert result == {"streaming_parser": {"subscriptions": 2}}
    assert _rows(db, "SELECT room_id, push_live, push_live_end, name FROM subscriptions ORDER BY room_id") == [
        (100, 1, 1, "目标-100"),
        (200, 1, 0, "旧名"),
    ]
    assert len(_backups(db, "subscriptions")) == 2


def test_bottle_meta_conversation_migrated(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _seed_minigame(root)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE mg_bottle SET meta=? WHERE id=1",
            (json.dumps({"mode": "normal", "conversation": OLD_GROUP}),),
        )
        conn.execute(
            "UPDATE mg_bottle SET meta=? WHERE id=2",
            (json.dumps({"mode": "anonymous", "conversation_id": OLD_USER}),),
        )
        insert = (
            "INSERT INTO mg_bottle (sender_id, sender_name, content, created_at, picked_by, "
            "status, meta) VALUES ('x', '', '坏', '2026-01-01 00:00:00', '', 'pooled', ?)"
        )
        conn.execute(insert, ("not-json",))
        conn.execute(insert, (json.dumps({"conversation": OPENID_GROUP}),))
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root,
        user_map={OLD_USER: OPENID_USER, OLD_USER2: OPENID_USER2},
        group_map={OLD_GROUP: OPENID_GROUP},
        official_only=True,
        logger=log,
    )

    # 用户级读写 3 处（sender×2 + picked×1）+ meta 2 行
    assert result["minigame"]["mg_bottle"] == 5
    assert json.loads(_scalar(db, "SELECT meta FROM mg_bottle WHERE id=1"))["conversation"] == OPENID_GROUP
    assert json.loads(_scalar(db, "SELECT meta FROM mg_bottle WHERE id=2"))["conversation_id"] == OPENID_USER
    # 坏 JSON 原样保留、已 openid 的不动
    metas = _rows(db, "SELECT meta FROM mg_bottle ORDER BY id")
    assert metas[2][0] == "not-json"
    assert json.loads(metas[3][0])["conversation"] == OPENID_GROUP


def test_missing_table_skips_only_that_table(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _db(root, "streaming_parser", "streaming_parser.db")
    _create(db, _STREAMING_PARSER_DDL.split("CREATE TABLE group_settings")[0])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO subscriptions (group_id, platform, room_id, short_id, uid, name, "
            "avatar_url, push_live, push_live_end, created_at, updated_at) "
            "VALUES (?, 'bilibili', 100, 0, 0, '旧', '', 1, 0, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            (OLD_GROUP,),
        )
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root, user_map={}, group_map={OLD_GROUP: OPENID_GROUP}, official_only=True, logger=log
    )

    assert result == {"streaming_parser": {"subscriptions": 1}}
    assert _rows(db, "SELECT group_id FROM subscriptions") == [(OPENID_GROUP,)]
    assert [r for r in log.records if r[0] == "warning"] == []
    assert any(level == "debug" and kw.get("table") == "group_settings" for level, _msg, kw in log.records)


def test_missing_column_skips_only_that_table(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    db = _db(root, "minigame", "minigame.db")
    ddl = _MINIGAME_DDL.replace("    conversation_id VARCHAR(128) NOT NULL DEFAULT '',\n", "")
    assert "conversation_id" not in ddl
    _create(db, ddl)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO mg_profile (user_id, user_name, score, best_score, plays, wins, "
            "updated_at) VALUES (?, '', 1, 1, 1, 0, '2026-01-01 00:00:00')",
            (OLD_USER,),
        )
        conn.execute(
            "INSERT INTO mg_record (user_id, game_id, score, created_at) VALUES (?, 'g1', 3, '2026-01-01 00:00:00')",
            (OLD_USER,),
        )
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root, user_map={OLD_USER: OPENID_USER}, group_map={}, official_only=True, logger=log
    )

    # conversation_id 缺列只跳过那一张表的会话改写，user_id 已改好
    assert result == {"minigame": {"mg_profile": 1, "mg_record": 1}}
    assert _scalar(db, "SELECT user_id FROM mg_record") == OPENID_USER
    assert [r for r in log.records if r[0] == "warning"] == []
    assert any(level == "debug" and kw.get("table") == "mg_record" for level, _msg, kw in log.records)


def test_broken_database_only_warns_and_others_still_migrate(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    broken = _db(root, "streaming_parser", "streaming_parser.db")
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"not a sqlite database")
    _seed_starship(root)
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root, user_map={OLD_USER: OPENID_USER}, group_map={}, official_only=True, logger=log
    )

    assert result == {"starship": {"starship_scores": 1}}
    warnings = [r for r in log.records if r[0] == "warning"]
    assert len(warnings) == 1
    assert warnings[0][2]["plugin"] == "streaming_parser"
    assert warnings[0][2]["error"]


_BUILTIN_PLUGINS = Path(__file__).resolve().parents[3] / "src" / "neobot_app" / "builtin_plugins"
#: 声明了插件 SQLite 但不迁身份列的插件：新增插件必须二选一（加 _DATABASES 或登记原因）。
_ALLOWED_UNMIGRATED: dict[str, str] = {}


def test_database_inventory_covers_builtin_plugins() -> None:
    declared = {
        path.relative_to(_BUILTIN_PLUGINS).parts[0]
        for path in _BUILTIN_PLUGINS.rglob("*.py")
        if "sqlite_database(" in path.read_text(encoding="utf-8")
    }
    covered = {name for name, _relative in _DATABASES}
    assert declared == covered | set(_ALLOWED_UNMIGRATED), (
        "内置插件新增/改名了独立库：登记到 _DATABASES 或写入 _ALLOWED_UNMIGRATED 理由"
    )
    assert all(reason.strip() for reason in _ALLOWED_UNMIGRATED.values())
    assert set(_MIGRATORS) == covered
    for name, relative in _DATABASES:
        assert relative.startswith(f"{name}/databases/"), relative
        assert relative.endswith(".db"), relative


def test_speaking_schedule_config_overrides_migrated(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    directory = _seed_speaking_schedule(
        root,
        [("group", OLD_GROUP), ("private", OLD_USER), ("group", NORMAL_QQ), ("group", OLD_GROUP2)],
    )
    original = (directory / "config.toml").read_bytes()
    log = _RecordingLogger()
    maps = dict(
        user_map={OLD_USER: OPENID_USER},
        group_map={OLD_GROUP: OPENID_GROUP, OLD_GROUP2: OPENID_GROUP},
    )

    result = migrate_plugin_databases(root, official_only=True, logger=log, **maps)

    # OLD_GROUP / OLD_GROUP2 映射到同一会话 → 只留第一条（插件校验不允许重复）
    assert result == {"speaking_schedule": {"config.toml": 3}}
    assert _config_overrides(root) == [
        ("group", OPENID_GROUP),
        ("private", OPENID_USER),
        ("group", NORMAL_QQ),
    ]
    backups = _identity_backups(directory, "config.toml")
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert any("重复" in msg for level, msg, _kw in log.records if level == "warning")
    # 幂等：第二次不写、不再备份
    assert migrate_plugin_databases(root, official_only=True, **maps) == {}
    assert len(_identity_backups(directory, "config.toml")) == 1


def test_speaking_schedule_mutes_migrated(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    deadlines = {
        "default": "2026-01-01T00:00:00+00:00",
        f"group:{OLD_GROUP}": "2026-03-01T00:00:00+00:00",
        f"group:{OLD_GROUP2}": "2026-02-01T00:00:00+00:00",
        f"private:{OLD_USER}": "2026-04-01T00:00:00+00:00",
        f"group:{NORMAL_QQ}": "2026-05-01T00:00:00+00:00",
    }
    directory = _seed_speaking_schedule(root, [], {"bot-1": deadlines})
    original = (directory / "mutes.json").read_bytes()

    result = migrate_plugin_databases(
        root,
        user_map={OLD_USER: OPENID_USER},
        group_map={OLD_GROUP: OPENID_GROUP, OLD_GROUP2: OPENID_GROUP},
        official_only=True,
    )

    assert result == {"speaking_schedule": {"mutes.json": 3}}
    data = json.loads((directory / "mutes.json").read_text(encoding="utf-8"))
    # 撞 key 取较晚截止时间；default / 无映射 scope / 已 openid 原样
    assert data["bot-1"] == {
        "default": "2026-01-01T00:00:00+00:00",
        f"group:{OPENID_GROUP}": "2026-03-01T00:00:00+00:00",
        f"private:{OPENID_USER}": "2026-04-01T00:00:00+00:00",
        f"group:{NORMAL_QQ}": "2026-05-01T00:00:00+00:00",
    }
    backups = _identity_backups(directory, "mutes.json")
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_speaking_schedule_bad_files_only_warn(tmp_path: Path) -> None:
    root = tmp_path / "plugins_data"
    directory = root / "speaking_schedule"
    directory.mkdir(parents=True)
    bad_toml = "[[overrides]\nid = "
    bad_json = "{not json"
    (directory / "config.toml").write_text(bad_toml, encoding="utf-8")
    (directory / "mutes.json").write_text(bad_json, encoding="utf-8")
    _seed_starship(root)
    log = _RecordingLogger()

    result = migrate_plugin_databases(
        root, user_map={OLD_USER: OPENID_USER}, group_map={}, official_only=True, logger=log
    )

    # 坏文件不抛、原样保留；其它库照常迁移
    assert result == {"starship": {"starship_scores": 1}}
    assert (directory / "config.toml").read_text(encoding="utf-8") == bad_toml
    assert (directory / "mutes.json").read_text(encoding="utf-8") == bad_json
    assert not list(directory.glob("*.identity-backup-*"))
    warnings = [r for r in log.records if r[0] == "warning"]
    assert len(warnings) == 2
    assert all(kw.get("plugin") == "speaking_schedule" for _level, _msg, kw in warnings)
