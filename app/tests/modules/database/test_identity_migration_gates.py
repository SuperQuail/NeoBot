"""canonical 归一必须只认 trusted 映射；会话级迁移只在 official 模式执行。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from neobot_app.database.identity_data_migration import migrate_identity_data
from neobot_app.user_identity import (
    bind_user_identity,
    canonical_archive_key,
    canonical_group_id,
    canonical_user_id,
    link_group_number,
    link_user_qq,
)


def _bind(tmp_path: Path):
    bind_user_identity(tmp_path)
    return tmp_path


def test_canonical_user_only_uses_trusted_mapping(tmp_path: Path) -> None:
    _bind(tmp_path)
    try:
        qq = "123456789"
        assert link_user_qq("OPENID", qq, trusted=False)[0]
        assert canonical_user_id(qq) == qq
        assert canonical_archive_key("user_profile", qq) == qq
        assert link_user_qq("OPENID", qq, trusted=True)[0]
        assert canonical_user_id(qq) == "OPENID"
        assert canonical_archive_key("user_profile", qq) == "OPENID"
    finally:
        bind_user_identity(None)


def test_canonical_group_only_uses_trusted_mapping(tmp_path: Path) -> None:
    _bind(tmp_path)
    try:
        group = "987654321"
        assert link_group_number("GOPENID", group, trusted=False)[0]
        assert canonical_group_id(group) == group
        assert link_group_number("GOPENID", group, trusted=True)[0]
        assert canonical_group_id(group) == "GOPENID"
    finally:
        bind_user_identity(None)


def _migration_fixture(root: Path) -> tuple[Path, Path]:
    data = root / "data"
    data.mkdir(parents=True)
    (data / "qqbot").mkdir()
    (data / "qqbot" / "identities.json").write_text("{}", encoding="utf-8")
    (data / "user_qq_map.json").write_text(
        json.dumps(
            {
                "version": 3,
                "aliases": {
                    "user:official:OPENID": {"qq": 123456789, "trusted": True},
                    "group:official:GOPENID": {"qq": 987654321, "trusted": True},
                },
            }
        ),
        encoding="utf-8",
    )
    db = root / "neobot.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE user_data (user_id TEXT PRIMARY KEY, profile TEXT);
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY, event_id TEXT UNIQUE, conversation_kind TEXT,
            conversation_id TEXT, sender_id TEXT, text TEXT
        );
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY, conversation_kind TEXT, conversation_id TEXT,
            speaker_id TEXT, content TEXT
        );
        CREATE TABLE model_usage_records (
            id INTEGER PRIMARY KEY, conversation_id TEXT, conversation_kind TEXT
        );
        CREATE TABLE archive_memories (
            id INTEGER PRIMARY KEY, table_name TEXT, key TEXT, value TEXT, tags TEXT,
            version INTEGER, updated_at TEXT
        );
        """
    )
    conn.execute("INSERT INTO messages VALUES (1,'e1','private','123456789','123456789','hi')")
    conn.execute("INSERT INTO memories VALUES (1,'private','123456789','123456789','m')")
    conn.execute("INSERT INTO model_usage_records VALUES (1,'123456789','private')")
    conn.execute(
        "INSERT INTO archive_memories VALUES (?,?,?,?,?,?,?)",
        (1, "memory_counter", "private:123456789", '{"count": 1, "messages": []}', "[]", 1, "t"),
    )
    conn.commit()
    conn.close()
    return data, db


def _conversation_ids(db: Path) -> tuple[str, str, str, str]:
    conn = sqlite3.connect(db)
    try:
        return (
            conn.execute("SELECT conversation_id FROM messages").fetchone()[0],
            conn.execute("SELECT conversation_id FROM memories").fetchone()[0],
            conn.execute("SELECT conversation_id FROM model_usage_records").fetchone()[0],
            conn.execute("SELECT key FROM archive_memories").fetchone()[0],
        )
    finally:
        conn.close()


def test_dual_mode_does_not_rewrite_conversation_level_data(tmp_path: Path) -> None:
    data, db = _migration_fixture(tmp_path)
    migrate_identity_data(db, data, official_only=False)
    assert _conversation_ids(db) == (
        "123456789",
        "123456789",
        "123456789",
        "private:123456789",
    )


def test_official_mode_rewrites_conversation_level_data(tmp_path: Path) -> None:
    data, db = _migration_fixture(tmp_path)
    migrate_identity_data(db, data, official_only=True)
    assert _conversation_ids(db) == ("OPENID", "OPENID", "OPENID", "private:OPENID")
