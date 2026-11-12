"""旧合成号 → openid 的数据库启动迁移测试。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.database.legacy_identity_migration import migrate_legacy_identity_ids

OLD_USER = "9000000000000"
OPENID_USER = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
OLD_GROUP = "9500000000000"
OPENID_GROUP = "9180DF39B12D4F45F9551E75800FDBC7"
NORMAL_QQ = "123456789"
_TIMESTAMP = "2026-01-01 00:00:00"


class _RecordingLogger:
    """记录日志调用，供断言冲突 WARNING。"""

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


def _make_db(path: Path) -> None:
    """用真实模型建全量表结构，防止迁移 SQL 与 schema 漂移。"""
    from sqlalchemy import create_engine

    from neobot_storage.models import Base

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def _write_identities(data_dir: Path) -> None:
    target = data_dir / "qqbot" / "identities.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "users": {OPENID_USER: int(OLD_USER)},
                "groups": {OPENID_GROUP: int(OLD_GROUP)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _insert_archive(conn: sqlite3.Connection, table_name: str, key: str) -> None:
    conn.execute(
        "INSERT INTO archive_memories "
        "(table_name, key, value, created_at, updated_at, version) VALUES (?, ?, ?, ?, ?, ?)",
        (table_name, key, "档案", _TIMESTAMP, _TIMESTAMP, 1),
    )


def _insert_snapshot(conn: sqlite3.Connection, table_name: str, key: str) -> None:
    conn.execute(
        "INSERT INTO archive_snapshots "
        "(table_name, key, value, total_chars, version, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (table_name, key, "快照", 2, 1, "manual", _TIMESTAMP),
    )


def _insert_cross_chat(
    conn: sqlite3.Connection,
    origin_kind: str,
    origin_id: str,
    target_kind: str,
    target_id: str,
    *,
    boot_id: str = "boot-1",
) -> None:
    conn.execute(
        "INSERT INTO cross_chat_sessions "
        "(origin_kind, origin_id, target_kind, target_id, boot_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (origin_kind, origin_id, target_kind, target_id, boot_id, _TIMESTAMP, _TIMESTAMP),
    )


def _insert_usage(conn: sqlite3.Connection, kind: str, conversation_id: str) -> None:
    conn.execute(
        "INSERT INTO model_usage_records "
        "(module_name, model_name, provider_name, input_tokens, output_tokens, "
        "cache_hit_tokens, cache_miss_tokens, cost_cny, conversation_kind, conversation_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("chat", "model", "provider", 1, 1, 0, 0, 0.0, kind, conversation_id, _TIMESTAMP),
    )


def _seed(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO user_data (user_id, nick_name, favorability) VALUES (?, ?, ?)",
            (OLD_USER, "旧用户", 7),
        )
        conn.execute(
            "INSERT INTO user_data (user_id, nick_name, favorability) VALUES (?, ?, ?)",
            (NORMAL_QQ, "普通用户", 1),
        )
        conn.execute(
            "INSERT INTO group_data (group_id, group_name, is_quite) VALUES (?, ?, 0)",
            (OLD_GROUP, "旧群"),
        )
        conn.execute(
            "INSERT INTO messages (event_id, conversation_kind, conversation_id, sender_id, "
            "sender_name, text, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("g1", "group", OLD_GROUP, OLD_USER, "旧用户", "群消息", _TIMESTAMP),
        )
        conn.execute(
            "INSERT INTO messages (event_id, conversation_kind, conversation_id, sender_id, "
            "sender_name, text, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p1", "private", OLD_USER, OLD_USER, "旧用户", "私聊消息", _TIMESTAMP),
        )
        conn.execute(
            "INSERT INTO memories (conversation_kind, conversation_id, speaker_id, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("group", OLD_GROUP, OLD_USER, "群记忆", _TIMESTAMP),
        )
        conn.execute(
            "INSERT INTO memories (conversation_kind, conversation_id, speaker_id, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("private", OLD_USER, OLD_USER, "个人记忆", _TIMESTAMP),
        )
        _insert_archive(conn, "user_profile", OLD_USER)
        _insert_archive(conn, "group_summary", OLD_GROUP)
        # 业务 key（不是本地 ID）必须原样保留
        _insert_archive(conn, "item_archive", OLD_USER)
        _insert_archive(conn, "memory_counter", f"private:{OLD_USER}")
        _insert_snapshot(conn, "user_profile", OLD_USER)
        _insert_cross_chat(conn, "private", OLD_USER, "group", OLD_GROUP)
        _insert_usage(conn, "group", OLD_GROUP)
        _insert_usage(conn, "private", OLD_USER)


def _scalar(db: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def test_migrates_all_identity_tables(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    _make_db(db)
    _seed(db)
    _write_identities(data_dir)
    log = _RecordingLogger()

    counts = migrate_legacy_identity_ids(db, data_dir, logger=log)

    assert counts == {
        "user_data": 1,
        "group_data": 1,
        "archive_memories": 3,
        "cross_chat_sessions": 1,
        "messages": 4,
        "memories": 4,
        "model_usage_records": 2,
        "archive_snapshots": 1,
    }
    # 资料/群资料的主键改写
    assert _scalar(db, "SELECT favorability FROM user_data WHERE user_id=?", (OPENID_USER,)) == 7
    assert _scalar(db, "SELECT COUNT(*) FROM user_data WHERE user_id=?", (OLD_USER,)) == 0
    assert _scalar(db, "SELECT group_name FROM group_data WHERE group_id=?", (OPENID_GROUP,)) == "旧群"
    # 消息：群会话换群 ID、私聊会话换用户 ID、发送者一律换用户 ID
    assert _scalar(db, "SELECT conversation_id FROM messages WHERE event_id='g1'") == OPENID_GROUP
    assert _scalar(db, "SELECT sender_id FROM messages WHERE event_id='g1'") == OPENID_USER
    assert _scalar(db, "SELECT conversation_id FROM messages WHERE event_id='p1'") == OPENID_USER
    # 记忆
    assert _scalar(db, "SELECT conversation_id FROM memories WHERE content='群记忆'") == OPENID_GROUP
    assert _scalar(db, "SELECT speaker_id FROM memories WHERE content='群记忆'") == OPENID_USER
    # 档案：身份表 key 改写，业务表 key 与普通用户数据不动
    rows = {(table_name, key) for table_name, key in _rows(db, "SELECT table_name, key FROM archive_memories")}
    assert ("user_profile", OPENID_USER) in rows
    assert ("group_summary", OPENID_GROUP) in rows
    assert ("item_archive", OLD_USER) in rows
    assert ("memory_counter", f"private:{OPENID_USER}") in rows
    assert ("user_profile", OLD_USER) not in rows
    assert _scalar(db, "SELECT COUNT(*) FROM archive_snapshots WHERE key=?", (OPENID_USER,)) == 1
    # 跨聊天会话两端
    assert _scalar(db, "SELECT origin_id FROM cross_chat_sessions") == OPENID_USER
    assert _scalar(db, "SELECT target_id FROM cross_chat_sessions") == OPENID_GROUP
    # 用量统计
    assert {row[0] for row in _rows(db, "SELECT conversation_id FROM model_usage_records")} == {
        OPENID_GROUP,
        OPENID_USER,
    }
    # 普通 QQ 数据不受影响
    assert _scalar(db, "SELECT nick_name FROM user_data WHERE user_id=?", (NORMAL_QQ,)) == "普通用户"
    # 成功迁移：有且仅有一条 INFO 汇总，无 WARNING/DEBUG 噪音
    assert [record for record in log.records if record[0] != "info"] == []
    infos = [(msg, kw) for level, msg, kw in log.records if level == "info" and "迁移完成" in msg]
    assert len(infos) == 1
    _msg, summary = infos[0]
    assert summary["migrated"] == sum(counts.values())
    assert summary["skipped"] == 0
    assert summary["tables"] == counts


def _rows(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    _make_db(db)
    _seed(db)
    _write_identities(data_dir)

    assert migrate_legacy_identity_ids(db, data_dir) != {}
    before = _rows(db, "SELECT user_id FROM user_data ORDER BY user_id")

    log = _RecordingLogger()
    assert migrate_legacy_identity_ids(db, data_dir, logger=log) == {}
    assert _rows(db, "SELECT user_id FROM user_data ORDER BY user_id") == before
    assert log.records == [], "无迁移无冲突时不得再记日志（避免每次启动刷屏）"


def test_missing_identities_file_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db)
    _seed(db)

    log = _RecordingLogger()
    assert migrate_legacy_identity_ids(db, tmp_path / "data", logger=log) == {}
    assert _scalar(db, "SELECT COUNT(*) FROM user_data WHERE user_id=?", (OLD_USER,)) == 1
    assert _scalar(db, "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (OLD_GROUP,)) == 1
    assert log.records == []


def test_missing_database_is_noop(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_identities(data_dir)
    db = tmp_path / "nope.db"

    log = _RecordingLogger()
    assert migrate_legacy_identity_ids(db, data_dir, logger=log) == {}
    assert not db.exists(), "迁移不能在库不存在时创建空库"
    assert log.records == []


def test_conflicts_are_skipped_not_deleted(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    _make_db(db)
    _write_identities(data_dir)
    with sqlite3.connect(db) as conn:
        # 旧行与新 openid 行同时存在 → 跳过旧行，两份数据都保留
        conn.execute("INSERT INTO user_data (user_id, favorability) VALUES (?, ?)", (OLD_USER, 7))
        conn.execute("INSERT INTO user_data (user_id, favorability) VALUES (?, ?)", (OPENID_USER, 3))
        _insert_archive(conn, "group_summary", OLD_GROUP)
        _insert_archive(conn, "group_summary", OPENID_GROUP)
        _insert_cross_chat(conn, "private", OLD_USER, "group", OLD_GROUP)
        _insert_cross_chat(conn, "private", OPENID_USER, "group", OPENID_GROUP)
    log = _RecordingLogger()

    counts = migrate_legacy_identity_ids(db, data_dir, logger=log)

    assert counts == {}
    assert _scalar(db, "SELECT favorability FROM user_data WHERE user_id=?", (OLD_USER,)) == 7
    assert _scalar(db, "SELECT favorability FROM user_data WHERE user_id=?", (OPENID_USER,)) == 3
    assert (
        _scalar(
            db,
            "SELECT COUNT(*) FROM archive_memories WHERE table_name='group_summary' AND key=?",
            (OLD_GROUP,),
        )
        == 1
    )
    assert (
        _scalar(
            db,
            "SELECT COUNT(*) FROM archive_memories WHERE table_name='group_summary' AND key=?",
            (OPENID_GROUP,),
        )
        == 1
    )
    assert _scalar(db, "SELECT COUNT(*) FROM cross_chat_sessions") == 2
    # 逐条冲突只记 DEBUG，不再刷 WARNING；结束时一条 INFO 汇总迁移/跳过条数
    assert [record for record in log.records if record[0] == "warning"] == []
    debug_tables = {kw.get("table") for level, _msg, kw in log.records if level == "debug"}
    assert {"user_data", "archive_memories", "cross_chat_sessions"} <= debug_tables
    infos = [(msg, kw) for level, msg, kw in log.records if level == "info"]
    assert len(infos) == 1
    _msg, summary = infos[0]
    assert "迁移完成" in _msg
    assert summary["migrated"] == 0
    assert summary["skipped"] == 3


def test_build_storage_migrates_between_schema_and_engine(monkeypatch: Any, tmp_path: Path) -> None:
    """bootstrap 顺序：备份 → schema 迁移 → 身份数据迁移 → 建引擎。"""
    from neobot_app.bootstrap.parts import core_reuse

    calls: list[str] = []
    monkeypatch.setattr(core_reuse, "backup_sqlite_database", lambda *a, **k: None)
    monkeypatch.setattr(core_reuse, "run_migrations", lambda url: calls.append("schema"))
    monkeypatch.setattr(
        core_reuse,
        "migrate_legacy_identity_ids",
        lambda db, data, **k: calls.append("identity") or {},
    )
    monkeypatch.setattr(core_reuse, "build_storage", lambda url: ("engine", "uow"))

    class _Factory:
        def get_logger(self, name: str) -> Logger:
            return NullLogger()

    result = core_reuse._build_storage(tmp_path / "neobot.db", "sqlite+aiosqlite:///x", _Factory())

    assert result == ("engine", "uow")
    assert calls == ["schema", "identity"]
