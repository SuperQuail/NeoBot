"""身份数据迁移（核心库 + agent 状态库）测试。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from neobot_app.database.identity_data_migration import (
    IdentityMigrationCoordinator,
    bind_identity_migration,
    get_identity_migration,
    migrate_identity_data,
)

TIMESTAMP = "2026-01-01 00:00:00"
NEWER_TIMESTAMP = "2026-02-01 00:00:00"
OLD_USER_A = "9000000000000"  # 旧 13 位合成号
OLD_USER_B = "9000000000001"
OLD_GROUP_A = "9500000000000"
OLD_QQ_USER = "3331347593"  # OneBot 时代的真实 QQ 号
OLD_QQ_GROUP = "983752344"  # OneBot 时代的真实群号
OPENID_A = "3380288042268959343"  # 官方 openid（真实数据里可以是纯数字）
OPENID_B = "1939BECB96D062817668DAFB030FCD6C"
OPENID_C = "2C5CB5A8C49B7C636CF672D97756FE6E"
GROUP_OPENID_A = "9180DF39B12D4F45F9551E75800FDBC7"
GROUP_OPENID_B = "926CB68DDDAB8C4EDB6618DFFDF37F2D"


class _RecordingLogger:
    """记录日志调用，供断言备份/汇总/失败告警。"""

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


def _make_core_db(path: Path) -> None:
    """用真实模型建表，迁移 SQL 与 schema 不会漂移。"""
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


def _write_mappings(data_dir: Path) -> None:
    identities = data_dir / "qqbot" / "identities.json"
    identities.parent.mkdir(parents=True, exist_ok=True)
    identities.write_text(
        json.dumps(
            {
                "users": {OPENID_A: int(OLD_USER_A), OPENID_B: int(OLD_USER_B)},
                "groups": {GROUP_OPENID_A: int(OLD_GROUP_A)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "user_qq_map.json").write_text(
        json.dumps(
            {
                "version": 3,
                "aliases": {
                    f"user:official:{OPENID_C}": {"qq": int(OLD_QQ_USER), "trusted": True},
                    f"group:official:{GROUP_OPENID_B}": {
                        "qq": int(OLD_QQ_GROUP),
                        "trusted": True,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _add_archive(conn: sqlite3.Connection, table_name: str, key: str, value: str, tags: str) -> None:
    conn.execute(
        "INSERT INTO archive_memories (table_name, key, value, tags, created_at, updated_at, version) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (table_name, key, value, tags, TIMESTAMP, TIMESTAMP),
    )


def _seed_core(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO user_data (user_id, nick_name, profile, age, favorability, "
            "avatar_fail_count, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (OLD_USER_A, "旧昵称", "旧资料", 20, 7, 2, TIMESTAMP),
                (OPENID_A, "新昵称", "新资料", 25, 3, 1, NEWER_TIMESTAMP),
                (OLD_USER_B, "移动用户", None, None, 4, 0, None),
                (OLD_QQ_USER, "QQ用户", None, None, 5, 0, None),
            ],
        )
        conn.executemany(
            "INSERT INTO group_data (group_id, group_name, profile, is_quite) VALUES (?, ?, ?, 0)",
            [
                (OLD_GROUP_A, "旧群名", "旧群资料"),
                (GROUP_OPENID_A, "新群名", "新群资料"),
                (OLD_QQ_GROUP, "QQ群", None),
            ],
        )
        _add_archive(conn, "user_profile", OLD_USER_A, "旧档案", '["a"]')
        _add_archive(conn, "user_profile", OPENID_A, "新档案", '["b"]')
        _add_archive(conn, "user_profile", OLD_USER_B, "移动档案", None)
        _add_archive(conn, "group_profile", OLD_GROUP_A, "群档案", None)
        _add_archive(conn, "item_archive", OLD_USER_A, "业务档案", None)
        _add_archive(
            conn,
            "memory_counter",
            f"private:{OLD_USER_A}",
            json.dumps({"count": 3, "messages": [{"sender_id": "1", "text": "m1"}]}),
            None,
        )
        _add_archive(
            conn,
            "memory_counter",
            f"private:{OPENID_A}",
            json.dumps({"count": 2, "messages": [{"sender_id": "2", "text": "m2"}]}),
            None,
        )
        _add_archive(
            conn, "memory_counter", f"group:{OLD_GROUP_A}", json.dumps({"count": 1}), None
        )
        conn.executemany(
            "INSERT INTO archive_snapshots (table_name, key, value, total_chars, version, "
            "reason, created_at) VALUES (?, ?, '快照', 2, 1, 'manual', ?)",
            [("user_profile", OLD_USER_A, TIMESTAMP), ("user_profile", OPENID_A, TIMESTAMP)],
        )
        conn.executemany(
            "INSERT INTO messages (event_id, conversation_kind, conversation_id, sender_id, "
            "sender_name, text, occurred_at) VALUES (?, ?, ?, ?, '人', '内容', ?)",
            [
                ("g1", "group", OLD_GROUP_A, OLD_USER_A, TIMESTAMP),
                ("p1", "private", OLD_USER_A, OLD_USER_A, TIMESTAMP),
                ("p2", "private", OLD_QQ_USER, OLD_QQ_USER, TIMESTAMP),
            ],
        )
        conn.executemany(
            "INSERT INTO memories (conversation_kind, conversation_id, speaker_id, content, "
            "created_at) VALUES (?, ?, ?, '记忆', ?)",
            [
                ("group", OLD_GROUP_A, OLD_USER_A, TIMESTAMP),
                ("private", OLD_USER_A, OLD_USER_A, TIMESTAMP),
            ],
        )
        conn.executemany(
            "INSERT INTO model_usage_records (module_name, model_name, provider_name, "
            "input_tokens, output_tokens, cache_hit_tokens, cache_miss_tokens, cost_cny, "
            "conversation_kind, conversation_id, created_at) "
            "VALUES ('chat', 'm', 'p', 1, 1, 0, 0, 0.0, ?, ?, ?)",
            [
                ("group", OLD_GROUP_A, TIMESTAMP),
                ("private", OLD_QQ_USER, TIMESTAMP),
            ],
        )
        conn.execute(
            "INSERT INTO cross_chat_sessions (origin_kind, origin_id, target_kind, target_id, "
            "boot_id, created_at, updated_at) VALUES ('private', ?, 'group', ?, 'boot-1', ?, ?)",
            (OLD_USER_A, OLD_GROUP_A, TIMESTAMP, TIMESTAMP),
        )
        _insert_scheduled(conn)


def _insert_scheduled(conn: sqlite3.Connection) -> None:
    bindings = json.dumps(
        [
            {"kind": "group", "id": OLD_GROUP_A},
            {"kind": "private", "id": OLD_USER_A},
            {"kind": "bilibili", "id": "123"},
        ],
        ensure_ascii=False,
    )
    conn.execute(
        "INSERT INTO scheduled_tasks (task_uuid, title, detail, recurrence, start_at, end_at, "
        "bindings_json, metadata_json, completed_window_keys_json, state, created_at, "
        "updated_at, version) VALUES ('task-1', '提醒', '内容', 'once', ?, ?, ?, '{}', '[]', "
        "'active', ?, ?, 1)",
        (TIMESTAMP, TIMESTAMP, bindings, TIMESTAMP, TIMESTAMP),
    )
    conn.execute(
        "INSERT INTO completed_scheduled_tasks (task_uuid, title, detail, recurrence, "
        "start_at, end_at, bindings_json, metadata_json, completed_at, completion_reason, "
        "archived_payload_json) VALUES ('task-2', '已完成', '', 'once', ?, ?, ?, '{}', ?, "
        "'once', ?)",
        (
            TIMESTAMP,
            TIMESTAMP,
            bindings,
            TIMESTAMP,
            json.dumps({"title": "已完成", "bindings": json.loads(bindings)}),
        ),
    )


def _seed_agent(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        source_doc = {
            "todos": [
                {"content": "旧任务", "status": "pending"},
                {"content": "共同任务", "status": "pending"},
            ],
            "questions": [{"question_id": "q_old", "question": {"id": "q"}}],
            "plan": None,
            "goal": {"goal_id": "g_old", "revision": 1, "phase": "active"},
        }
        target_doc = {
            "todos": [{"content": "共同任务", "status": "in_progress"}],
            "questions": [],
            "plan": {"plan_id": "p_new", "status": "approved"},
            "goal": None,
        }
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'main', ?)",
            (
                f"group:{OLD_GROUP_A}:main",
                f"group:{OLD_GROUP_A}",
                json.dumps(source_doc, ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'main', ?)",
            (
                f"group:{GROUP_OPENID_A}:main",
                f"group:{GROUP_OPENID_A}",
                json.dumps(target_doc, ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'main', ?)",
            (
                f"private:{OLD_USER_A}:main",
                f"private:{OLD_USER_A}",
                json.dumps({"todos": [], "questions": [], "plan": None, "goal": None}),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'main', ?)",
            (
                f"private:{OLD_USER_B}:main",
                f"private:{OLD_USER_B}",
                json.dumps(
                    {
                        "todos": [{"content": "空目标旧任务", "status": "pending"}],
                        "questions": [],
                        "plan": None,
                        "goal": None,
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'main', '{}')",
            (f"private:{OPENID_B}:main", f"private:{OPENID_B}"),
        )
        # 两侧 plan/goal 都非空：保留目标状态机字段，文本按「旧 + 空行 + 新」拼接
        worker_source = {
            "todos": [],
            "questions": [],
            "plan": {"plan_id": "p_old", "status": "planning", "plan": "旧计划"},
            "goal": {
                "goal_id": "g_old2", "revision": 2, "phase": "active", "objective": "旧目标",
            },
        }
        worker_target = {
            "todos": [],
            "questions": [],
            "plan": {"plan_id": "p_new", "status": "approved", "plan": "新计划"},
            "goal": {
                "goal_id": "g_new", "revision": 1, "phase": "complete", "objective": "新目标",
            },
        }
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'worker', ?)",
            (
                f"group:{OLD_GROUP_A}:main",
                f"group:{OLD_GROUP_A}",
                json.dumps(worker_source, ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'worker', ?)",
            (
                f"group:{GROUP_OPENID_A}:main",
                f"group:{GROUP_OPENID_A}",
                json.dumps(worker_target, ensure_ascii=False),
            ),
        )
        # 目标 document 损坏：仍需合并源文档（至少保留源）
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'broken', ?)",
            (
                f"group:{OLD_GROUP_A}:main",
                f"group:{OLD_GROUP_A}",
                json.dumps(
                    {
                        "todos": [{"content": "损坏目标旧任务", "status": "pending"}],
                        "questions": [],
                        "plan": None,
                        "goal": None,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute(
            "INSERT INTO state VALUES (?, ?, 'broken', 'not-json')",
            (f"group:{GROUP_OPENID_A}:main", f"group:{GROUP_OPENID_A}"),
        )
        conn.execute(
            "INSERT INTO events (owner, chat, agent, name, created_at, metadata) "
            "VALUES (?, ?, 'main', 'tool', 1.0, '{}')",
            (f"private:{OLD_USER_A}:main", f"private:{OLD_USER_A}"),
        )
        conn.executemany(
            "INSERT INTO receipts VALUES (?, ?, 'mid-1')",
            [
                (f"group:{OLD_GROUP_A}:main", f"group:{OLD_GROUP_A}"),
                (f"group:{GROUP_OPENID_A}:main", f"group:{GROUP_OPENID_A}"),
            ],
        )


def _scalar(db: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def _rows(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def _table_exists(db: Path, table: str) -> bool:
    return bool(
        _scalar(
            db,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
    )


def test_migrates_core_and_agent_data(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    agent_db = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    _make_core_db(db)
    _make_agent_db(agent_db)
    _seed_core(db)
    _seed_agent(agent_db)
    _write_mappings(data_dir)
    log = _RecordingLogger()

    counts = migrate_identity_data(db, data_dir, official_only=True, logger=log)

    assert counts == {
        "user_data": 3,
        "group_data": 2,
        "archive_memories": 5,
        "archive_snapshots": 1,
        "messages": 6,
        "memories": 4,
        "model_usage_records": 2,
        "cross_chat_sessions": 1,
        "scheduled_tasks": 1,
        "completed_scheduled_tasks": 1,
        "agent_state": 5,
        "agent_events": 1,
        "agent_receipts": 1,
    }
    # user_data：两边都有 → 合并并删除旧行；只有旧行 → 整行移动
    assert _scalar(db, "SELECT profile FROM user_data WHERE user_id=?", (OPENID_A,)) == (
        "旧资料\n\n新资料"
    )
    assert _scalar(db, "SELECT nick_name FROM user_data WHERE user_id=?", (OPENID_A,)) == "新昵称"
    assert _scalar(db, "SELECT favorability FROM user_data WHERE user_id=?", (OPENID_A,)) == 7
    assert _scalar(db, "SELECT avatar_fail_count FROM user_data WHERE user_id=?", (OPENID_A,)) == 2
    assert _scalar(db, "SELECT age FROM user_data WHERE user_id=?", (OPENID_A,)) == 25
    assert _scalar(db, "SELECT fetched_at FROM user_data WHERE user_id=?", (OPENID_A,)) == NEWER_TIMESTAMP
    assert _scalar(db, "SELECT COUNT(*) FROM user_data WHERE user_id=?", (OLD_USER_A,)) == 0
    assert _scalar(db, "SELECT nick_name FROM user_data WHERE user_id=?", (OPENID_B,)) == "移动用户"
    assert _scalar(db, "SELECT nick_name FROM user_data WHERE user_id=?", (OPENID_C,)) == "QQ用户"
    assert _scalar(db, "SELECT COUNT(*) FROM user_data WHERE user_id=?", (OLD_QQ_USER,)) == 0
    # group_data
    assert _scalar(db, "SELECT profile FROM group_data WHERE group_id=?", (GROUP_OPENID_A,)) == (
        "旧群资料\n\n新群资料"
    )
    assert _scalar(db, "SELECT group_name FROM group_data WHERE group_id=?", (GROUP_OPENID_A,)) == "新群名"
    assert _scalar(db, "SELECT group_name FROM group_data WHERE group_id=?", (GROUP_OPENID_B,)) == "QQ群"
    # 档案：身份表合并/移动，业务表不动
    archive = {(name, key) for name, key in _rows(db, "SELECT table_name, key FROM archive_memories")}
    assert ("user_profile", OPENID_A) in archive
    assert ("user_profile", OLD_USER_A) not in archive
    assert ("user_profile", OPENID_B) in archive
    assert ("group_profile", GROUP_OPENID_A) in archive
    assert ("item_archive", OLD_USER_A) in archive
    value, tags, merged_version, merged_updated = _rows(
        db,
        "SELECT value, tags, version, updated_at FROM archive_memories "
        "WHERE table_name='user_profile' AND key=?",
        (OPENID_A,),
    )[0]
    assert value == "旧档案\n\n新档案"
    assert json.loads(tags) == ["a", "b"]
    # 合并覆盖目标行：version 递增、updated_at 刷新，面板乐观锁不会拿旧版本覆盖合并内容
    assert merged_version == 2
    assert merged_updated != TIMESTAMP
    with sqlite3.connect(db) as conn:
        stale = conn.execute(
            "UPDATE archive_memories SET value=value "
            "WHERE table_name='user_profile' AND key=? AND version=1",
            (OPENID_A,),
        )
        assert stale.rowcount == 0, "旧 version 的乐观锁写入必须失败"
        current = conn.execute(
            "UPDATE archive_memories SET value=value "
            "WHERE table_name='user_profile' AND key=? AND version=2",
            (OPENID_A,),
        )
        assert current.rowcount == 1
    # 计数器：key 改写到 openid；冲突时 count 相加、messages 拼接
    counter = _scalar(
        db, "SELECT value FROM archive_memories WHERE table_name='memory_counter' AND key=?",
        (f"private:{OPENID_A}",),
    )
    counter_value = json.loads(counter)
    assert counter_value["count"] == 5
    assert [item["text"] for item in counter_value["messages"]] == ["m1", "m2"]
    assert (
        _scalar(
            db,
            "SELECT version FROM archive_memories WHERE table_name='memory_counter' AND key=?",
            (f"private:{OPENID_A}",),
        )
        == 2
    )
    assert (
        _scalar(
            db,
            "SELECT COUNT(*) FROM archive_memories WHERE table_name='memory_counter' AND key=?",
            (f"group:{GROUP_OPENID_A}",),
        )
        == 1
    )
    # 快照：无唯一约束，直接改 key；重键后 version 同步成目标档案的当前 version
    assert _scalar(db, "SELECT COUNT(*) FROM archive_snapshots WHERE key=?", (OPENID_A,)) == 2
    assert _scalar(db, "SELECT COUNT(*) FROM archive_snapshots WHERE key=?", (OLD_USER_A,)) == 0
    assert (
        _scalar(db, "SELECT COUNT(*) FROM archive_snapshots WHERE key=? AND version=2", (OPENID_A,))
        == 1
    )
    # 消息 / 记忆：群会话换群 openid，私聊会话与发送者换用户 openid
    assert _scalar(db, "SELECT conversation_id FROM messages WHERE event_id='g1'") == GROUP_OPENID_A
    assert _scalar(db, "SELECT sender_id FROM messages WHERE event_id='g1'") == OPENID_A
    assert _scalar(db, "SELECT conversation_id FROM messages WHERE event_id='p1'") == OPENID_A
    assert _scalar(db, "SELECT sender_id FROM messages WHERE event_id='p2'") == OPENID_C
    assert _scalar(db, "SELECT conversation_id FROM memories WHERE conversation_kind='group'") == GROUP_OPENID_A
    assert _scalar(db, "SELECT speaker_id FROM memories WHERE conversation_kind='group'") == OPENID_A
    assert {row[0] for row in _rows(db, "SELECT conversation_id FROM model_usage_records")} == {
        GROUP_OPENID_A,
        OPENID_C,
    }
    assert _scalar(db, "SELECT origin_id FROM cross_chat_sessions") == OPENID_A
    assert _scalar(db, "SELECT target_id FROM cross_chat_sessions") == GROUP_OPENID_A
    # official_only=True：定时任务绑定迁移到 openid，bilibili 等其它 kind 不动
    bindings = _scalar(db, "SELECT bindings_json FROM scheduled_tasks")
    assert OLD_GROUP_A not in bindings
    assert GROUP_OPENID_A in bindings
    assert '"kind": "bilibili"' in bindings
    archived = _scalar(db, "SELECT archived_payload_json FROM completed_scheduled_tasks")
    assert OLD_USER_A not in archived
    # 备份：合并/删除前写入旧行 JSON
    backup = _rows(db, "SELECT table_name, old_key, new_key, payload FROM identity_migration_backup")
    assert ("user_data", OLD_USER_A, OPENID_A) in {(t, o, n) for t, o, n, _p in backup}
    assert any(table == "user_data" and "旧资料" in payload for table, _o, _n, payload in backup)
    assert any(table == "archive_memories" and "旧档案" in payload for table, _o, _n, payload in backup)
    agent_backup = _rows(
        agent_db, "SELECT table_name, payload FROM identity_migration_backup"
    )
    assert any(table == "state" and "旧任务" in payload for table, payload in agent_backup)
    assert any(table == "receipts" for table, _payload in agent_backup)
    # agent 状态：目标行合并文档（todos 并集、plan 目标优先、goal 旧值补位）
    merged_doc = json.loads(
        _scalar(
            agent_db,
            "SELECT document FROM state WHERE owner=? AND chat=? AND agent='main'",
            (f"group:{GROUP_OPENID_A}:main", f"group:{GROUP_OPENID_A}"),
        )
    )
    assert [item["content"] for item in merged_doc["todos"]] == ["共同任务", "旧任务"]
    assert merged_doc["plan"]["plan_id"] == "p_new"
    assert merged_doc["goal"]["goal_id"] == "g_old"
    assert [q["question_id"] for q in merged_doc["questions"]] == ["q_old"]
    # 两侧 plan/goal 都非空：状态机字段取目标，文本旧在前拼接
    worker_doc = json.loads(
        _scalar(
            agent_db,
            "SELECT document FROM state WHERE owner=? AND agent='worker'",
            (f"group:{GROUP_OPENID_A}:main",),
        )
    )
    assert worker_doc["plan"]["plan_id"] == "p_new"
    assert worker_doc["plan"]["plan"] == "旧计划\n\n新计划"
    assert worker_doc["goal"]["goal_id"] == "g_new"
    assert worker_doc["goal"]["objective"] == "旧目标\n\n新目标"
    # 目标 document 损坏：按空文档合并源文档，源内容不丢；损坏原文进备份
    broken_doc = json.loads(
        _scalar(
            agent_db,
            "SELECT document FROM state WHERE owner=? AND agent='broken'",
            (f"group:{GROUP_OPENID_A}:main",),
        )
    )
    assert [item["content"] for item in broken_doc["todos"]] == ["损坏目标旧任务"]
    assert any(
        table == "state" and "not-json" in payload for table, payload in agent_backup
    )
    assert (
        _scalar(
            agent_db,
            "SELECT COUNT(*) FROM state WHERE owner=?",
            (f"group:{OLD_GROUP_A}:main",),
        )
        == 0
    )
    assert (
        _scalar(
            agent_db, "SELECT COUNT(*) FROM state WHERE owner=?", (f"private:{OPENID_A}:main",)
        )
        == 1
    )
    # 目标文档是合法空对象：旧文档内容合并进去而不是被空目标覆盖
    empty_target_doc = json.loads(
        _scalar(
            agent_db, "SELECT document FROM state WHERE owner=?", (f"private:{OPENID_B}:main",)
        )
    )
    assert [item["content"] for item in empty_target_doc["todos"]] == ["空目标旧任务"]
    assert (
        _scalar(agent_db, "SELECT owner FROM events") == f"private:{OPENID_A}:main"
    )
    assert _rows(agent_db, "SELECT owner, message_id FROM receipts") == [
        (f"group:{GROUP_OPENID_A}:main", "mid-1")
    ]
    # 只汇总一条 INFO，无 WARNING
    infos = [(msg, kw) for level, msg, kw in log.records if level == "info"]
    assert len(infos) == 1 and "身份数据迁移完成" in infos[0][0]
    warnings = [record for record in log.records if record[0] == "warning"]
    # official 迁移会为没有 openid 映射的活跃任务/跨聊天会话输出 WARNING（fixture 含 1 条）。
    assert all(
        "缺少 openid 映射" in message or "跨聊天" in message
        for _level, message, _kw in warnings
    )


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    agent_db = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    _make_core_db(db)
    _make_agent_db(agent_db)
    _seed_core(db)
    _seed_agent(agent_db)
    _write_mappings(data_dir)

    assert migrate_identity_data(db, data_dir) != {}
    before = (
        _rows(db, "SELECT user_id FROM user_data ORDER BY user_id"),
        _rows(db, "SELECT key FROM archive_memories ORDER BY key"),
        _rows(db, "SELECT event_id, conversation_id, sender_id FROM messages ORDER BY event_id"),
        _scalar(db, "SELECT COUNT(*) FROM identity_migration_backup"),
        _scalar(agent_db, "SELECT COUNT(*) FROM state"),
    )
    log = _RecordingLogger()

    assert migrate_identity_data(db, data_dir, logger=log) == {}
    after = (
        _rows(db, "SELECT user_id FROM user_data ORDER BY user_id"),
        _rows(db, "SELECT key FROM archive_memories ORDER BY key"),
        _rows(db, "SELECT event_id, conversation_id, sender_id FROM messages ORDER BY event_id"),
        _scalar(db, "SELECT COUNT(*) FROM identity_migration_backup"),
        _scalar(agent_db, "SELECT COUNT(*) FROM state"),
    )
    assert after == before
    assert log.records == [], "无迁移时不得刷日志"


def test_scheduled_bindings_rewritten_only_in_official_mode(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    _make_core_db(db)
    with sqlite3.connect(db) as conn:
        _insert_scheduled(conn)
    _write_mappings(data_dir)

    assert migrate_identity_data(db, data_dir, official_only=False) == {}
    assert OLD_GROUP_A in _scalar(db, "SELECT bindings_json FROM scheduled_tasks")

    counts = migrate_identity_data(db, data_dir, official_only=True)

    assert counts == {"scheduled_tasks": 1, "completed_scheduled_tasks": 1}
    bindings = json.loads(_scalar(db, "SELECT bindings_json FROM scheduled_tasks"))
    assert bindings == [
        {"kind": "group", "id": GROUP_OPENID_A},
        {"kind": "private", "id": OPENID_A},
        {"kind": "bilibili", "id": "123"},
    ]
    archived = json.loads(
        _scalar(db, "SELECT archived_payload_json FROM completed_scheduled_tasks")
    )
    assert archived["bindings"] == bindings
    # 再次执行幂等
    assert migrate_identity_data(db, data_dir, official_only=True) == {}


def test_missing_mapping_files_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    _make_core_db(db)
    _seed_core(db)

    assert migrate_identity_data(db, tmp_path / "data") == {}
    assert _scalar(db, "SELECT COUNT(*) FROM user_data WHERE user_id=?", (OLD_USER_A,)) == 1
    assert not _table_exists(db, "identity_migration_backup"), "no-op 不应建备份表"


def test_failure_logs_warning_without_raising(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_mappings(data_dir)
    db = tmp_path / "neobot.db"
    db.write_bytes(b"not a sqlite database")
    log = _RecordingLogger()

    assert migrate_identity_data(db, data_dir, logger=log) == {}
    assert any(level == "warning" for level, _msg, _kw in log.records)


@pytest.mark.asyncio
async def test_coordinator_runs_migration_in_thread(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    data_dir = tmp_path / "data"
    _make_core_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO user_data (user_id, nick_name, favorability) VALUES (?, '移动用户', 0)",
            (OLD_USER_B,),
        )
    _write_mappings(data_dir)
    coordinator = IdentityMigrationCoordinator(
        db_path=db, data_dir=data_dir, logger=_RecordingLogger()
    )

    bind_identity_migration(coordinator)
    try:
        assert get_identity_migration() is coordinator
        assert await coordinator.run() == {"user_data": 1}
    finally:
        bind_identity_migration(None)
    assert get_identity_migration() is None
    assert _scalar(db, "SELECT nick_name FROM user_data WHERE user_id=?", (OPENID_B,)) == "移动用户"

    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not a sqlite database")
    failing = IdentityMigrationCoordinator(
        db_path=broken, data_dir=data_dir, logger=_RecordingLogger()
    )
    assert await failing.run() == {}


def test_agent_state_migrates_without_core_db(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    agent_db = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    _make_agent_db(agent_db)
    _seed_agent(agent_db)
    _write_mappings(data_dir)

    counts = migrate_identity_data(tmp_path / "missing.db", data_dir)

    assert counts == {"agent_state": 5, "agent_events": 1, "agent_receipts": 1}
