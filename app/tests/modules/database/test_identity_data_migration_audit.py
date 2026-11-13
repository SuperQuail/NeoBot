"""身份迁移审计修复的回归测试（备份快照/插件门控/用量分 kind/未映射告警）。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from neobot_app.database.identity_data_migration import (
    IdentityMigrationCoordinator,
    migrate_identity_data,
)

TIMESTAMP = "2026-01-01 00:00:00"
OLD_USER = "9000000000000"
OLD_GROUP = "9500000000000"
OLD_QQ_USER = "3331347593"
OPENID_USER = "1939BECB96D062817668DAFB030FCD6C"
OPENID_GROUP = "9180DF39B12D4F45F9551E75800FDBC7"
STRAY_QQ = "3771742727"


class _RecordingLogger:
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

    def messages(self, level: str) -> list[str]:
        return [msg for record_level, msg, _kw in self.records if record_level == level]


def _make_core_db(path: Path) -> None:
    from sqlalchemy import create_engine

    from neobot_storage.models import Base

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def _make_agent_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (
                owner TEXT NOT NULL, chat TEXT NOT NULL, agent TEXT NOT NULL,
                document TEXT NOT NULL, PRIMARY KEY(owner,chat,agent));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, chat TEXT NOT NULL,
                agent TEXT NOT NULL, name TEXT NOT NULL, created_at REAL NOT NULL,
                metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts (
                owner TEXT NOT NULL, chat TEXT NOT NULL, message_id TEXT NOT NULL,
                PRIMARY KEY(owner,chat,message_id));
            """
        )


def _make_plugin_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT NOT NULL,
                platform TEXT NOT NULL, room_id TEXT NOT NULL,
                push_live INTEGER NOT NULL DEFAULT 1, push_live_end INTEGER NOT NULL DEFAULT 1,
                created_at TEXT, updated_at TEXT,
                UNIQUE(group_id, platform, room_id));
            CREATE TABLE IF NOT EXISTS group_settings (
                group_id TEXT PRIMARY KEY, card_style TEXT,
                ai_reply_live INTEGER DEFAULT 0, ai_reply_live_end INTEGER DEFAULT 0,
                default_push_live INTEGER DEFAULT 1, default_push_live_end INTEGER DEFAULT 1,
                updated_at TEXT);
            """
        )


def _write_mappings(data_dir: Path) -> None:
    identities = data_dir / "qqbot" / "identities.json"
    identities.parent.mkdir(parents=True, exist_ok=True)
    identities.write_text(
        json.dumps(
            {"users": {OPENID_USER: int(OLD_USER)}, "groups": {OPENID_GROUP: int(OLD_GROUP)}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "user_qq_map.json").write_text(
        json.dumps(
            {
                "version": 3,
                "aliases": {
                    f"user:official:{OPENID_USER}": {"qq": int(OLD_QQ_USER), "trusted": True}
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_overlap_mappings(data_dir: Path) -> None:
    """同一个数字既是用户 QQ 又是群号：验证用量表按 conversation_kind 分流。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "user_qq_map.json").write_text(
        json.dumps(
            {
                "version": 3,
                "aliases": {
                    f"user:official:{OPENID_USER}": {"qq": 10001, "trusted": True},
                    f"group:official:{OPENID_GROUP}": {"qq": 10001, "trusted": True},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _scalar(db: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def _rows(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def _snapshot_names(data_dir: Path, stem: str) -> list[str]:
    return sorted(item.name for item in (data_dir / "db_backup").glob(f"identity_{stem}_*.db"))


def _seed_profile_move(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO user_data (user_id, nick_name, favorability) VALUES (?, '旧用户', 0)",
            (OLD_USER,),
        )


def test_aux_snapshots_use_identity_prefix_and_do_not_prune_startup_backups(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    agent_db = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    plugin_db = data_dir / "plugins_data" / "streaming_parser" / "databases" / "streaming_parser.db"
    _make_core_db(db)
    _seed_profile_move(db)
    _make_agent_db(agent_db)
    _make_plugin_db(plugin_db)
    _write_mappings(data_dir)
    backup_dir = data_dir / "db_backup"
    backup_dir.mkdir(parents=True)
    startup_backup = backup_dir / "neobot_20260101_000000_000_keepme.db"
    startup_backup.write_bytes(b"startup backup")
    for index in range(6):
        (backup_dir / f"identity_agent_state_20000101_000000_000_dummy{index}.db").write_bytes(
            b"old"
        )

    counts = migrate_identity_data(db, data_dir, logger=_RecordingLogger())

    assert counts.get("user_data") == 1
    assert _snapshot_names(data_dir, "agent_state"), "agent 状态库迁移前必须先快照"
    assert len(_snapshot_names(data_dir, "agent_state")) == 5, "identity_ 快照只保留最近 5 份"
    assert _snapshot_names(data_dir, "streaming_parser"), "插件库迁移前必须先快照"
    assert startup_backup.exists(), "identity_ 快照轮转不得挤掉启动备份"
    assert not _snapshot_names(data_dir, "neobot"), "启动路径核心库已有备份，入口不再重复快照"
    newest = max(
        (backup_dir / name for name in _snapshot_names(data_dir, "agent_state")),
        key=lambda item: item.stat().st_mtime_ns,
    )
    with sqlite3.connect(newest) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='state'").fetchone()[0]


def test_coordinator_snapshots_core_agent_and_plugin_before_online_run(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    agent_db = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    plugin_db = data_dir / "plugins_data" / "streaming_parser" / "databases" / "streaming_parser.db"
    _make_core_db(db)
    _seed_profile_move(db)
    _make_agent_db(agent_db)
    _make_plugin_db(plugin_db)
    _write_mappings(data_dir)
    coordinator = IdentityMigrationCoordinator(
        db_path=db, data_dir=data_dir, logger=_RecordingLogger()
    )

    counts = __import__("asyncio").run(coordinator.run())

    assert counts.get("user_data") == 1
    assert _snapshot_names(data_dir, "neobot"), "在线迁移必须补拍核心库快照"
    assert _snapshot_names(data_dir, "agent_state")
    assert _snapshot_names(data_dir, "streaming_parser")
    # 协调器已整体快照，入口不再重复拍 agent/插件快照
    assert len(_snapshot_names(data_dir, "agent_state")) == 1


def test_plugin_migration_skipped_when_not_official_only(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    plugin_db = data_dir / "plugins_data" / "streaming_parser" / "databases" / "streaming_parser.db"
    _make_core_db(db)
    _make_plugin_db(plugin_db)
    with sqlite3.connect(plugin_db) as conn:
        conn.execute(
            "INSERT INTO subscriptions (group_id, platform, room_id) VALUES (?, 'bilibili', '1')",
            (OLD_GROUP,),
        )
        conn.execute(
            "INSERT INTO group_settings (group_id, card_style, updated_at) VALUES (?, 'card', ?)",
            (OLD_GROUP, TIMESTAMP),
        )
    _write_mappings(data_dir)

    assert migrate_identity_data(db, data_dir, official_only=False) == {}
    assert _scalar(plugin_db, "SELECT group_id FROM subscriptions") == OLD_GROUP
    assert _scalar(plugin_db, "SELECT group_id FROM group_settings") == OLD_GROUP

    counts = migrate_identity_data(db, data_dir, official_only=True)

    assert counts == {
        "plugin:streaming_parser:subscriptions": 1,
        "plugin:streaming_parser:group_settings": 1,
    }
    assert _scalar(plugin_db, "SELECT group_id FROM subscriptions") == OPENID_GROUP
    assert _scalar(plugin_db, "SELECT group_id FROM group_settings") == OPENID_GROUP


def test_model_usage_records_split_by_conversation_kind(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    _make_core_db(db)
    _write_overlap_mappings(data_dir)
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO model_usage_records (module_name, model_name, provider_name, "
            "input_tokens, output_tokens, cache_hit_tokens, cache_miss_tokens, cost_cny, "
            "conversation_kind, conversation_id, created_at) "
            "VALUES ('chat', 'm', 'p', 1, 1, 0, 0, 0.0, ?, ?, ?)",
            [("private", "10001", TIMESTAMP), ("group", "10001", TIMESTAMP), (None, "10001", TIMESTAMP)],
        )

    counts = migrate_identity_data(db, data_dir, official_only=True)

    assert counts.get("model_usage_records") == 2, "只改有 kind 的 private/group 两行"
    rows = dict(
        _rows(db, "SELECT conversation_kind, conversation_id FROM model_usage_records")
    )
    assert rows["private"] == OPENID_USER
    assert rows["group"] == OPENID_GROUP
    assert rows[None] == "10001", "无 kind 的行不得被混合映射误改"


def test_official_mode_warns_about_unmapped_scheduled_and_cross_chat(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    _make_core_db(db)
    _write_mappings(data_dir)
    bindings = [
        {"kind": "group", "id": OLD_GROUP},
        {"kind": "private", "id": STRAY_QQ},
        {"kind": "group", "id": "111111"},
    ]
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks (task_uuid, title, detail, recurrence, start_at, end_at, "
            "bindings_json, metadata_json, completed_window_keys_json, state, created_at, "
            "updated_at, version) VALUES ('task-unmapped', '提醒', '', 'once', ?, ?, ?, '{}', "
            "'[]', 'active', ?, ?, 1)",
            (TIMESTAMP, TIMESTAMP, json.dumps(bindings), TIMESTAMP, TIMESTAMP),
        )
        conn.execute(
            "INSERT INTO cross_chat_sessions (origin_kind, origin_id, target_kind, target_id, "
            "boot_id, created_at, updated_at) VALUES ('private', ?, 'group', ?, 'boot-1', ?, ?)",
            (STRAY_QQ, OLD_GROUP, TIMESTAMP, TIMESTAMP),
        )
    log = _RecordingLogger()

    migrate_identity_data(db, data_dir, official_only=True, logger=log)

    scheduled_warnings = [msg for msg in log.messages("warning") if "定时任务绑定" in msg]
    assert len(scheduled_warnings) == 1
    record = next(kw for level, msg, kw in log.records if level == "warning" and "定时任务绑定" in msg)
    assert record["tasks"] == 1
    assert record["bindings"] == 2, "真实号规模的 group 111111 与 private STRAY_QQ 都要计入"
    assert record["task_uuids"] == ["task-unmapped"]
    assert any("跨聊天会话" in msg for msg in log.messages("warning"))
    # 可映射的 binding 已改写；未映射的原样保留（留给 /linkqq、/linkgroup 后再迁移）
    rewritten = json.loads(_scalar(db, "SELECT bindings_json FROM scheduled_tasks"))
    assert rewritten[0]["id"] == OPENID_GROUP
    assert rewritten[1]["id"] == STRAY_QQ

    quiet_db = tmp_path / "quiet.db"
    _make_core_db(quiet_db)
    with sqlite3.connect(quiet_db) as conn:
        conn.execute(
            "INSERT INTO cross_chat_sessions (origin_kind, origin_id, target_kind, target_id, "
            "boot_id, created_at, updated_at) VALUES ('private', ?, 'group', ?, 'boot-1', ?, ?)",
            (STRAY_QQ, OLD_GROUP, TIMESTAMP, TIMESTAMP),
        )
    quiet_log = _RecordingLogger()
    migrate_identity_data(quiet_db, data_dir, official_only=False, logger=quiet_log)
    assert [msg for msg in quiet_log.messages("warning") if "缺少 openid 映射" in msg] == []


def test_snapshot_failure_only_warns(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = tmp_path / "neobot.db"
    db.write_bytes(b"not a sqlite database")
    _write_mappings(data_dir)
    log = _RecordingLogger()
    coordinator = IdentityMigrationCoordinator(db_path=db, data_dir=data_dir, logger=log)

    assert __import__("asyncio").run(coordinator.run()) == {}
    assert any(level == "warning" for level, _msg, _kw in log.records)
