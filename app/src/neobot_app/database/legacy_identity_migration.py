"""启动时把本体数据库里的旧合成号本地 ID 一次性改写成官方 openid。

官方通道早期把 openid 派生为 13 位合成号当本地主键写库；现在主键直接是
openid。定时任务（runtime.legacy_bindings）与 user_qq_map 已在运行时迁移，
但 user_data / messages / 档案 / 跨聊天记录 / 用量统计里仍是旧合成号，升级后
按 openid 查不到这些数据。

迁移源是 <DATA_DIR>/qqbot/identities.json（适配器持久化的 openid ↔ 合成号，
只读）；文件缺失或损坏时不动数据库（no-op）。整个迁移在一个 SQLite 事务里
完成，逐条先查后改：目标 openid 行已存在时逐条记 DEBUG 并跳过该条，不删除任何
旧行（留给人工合并）。重复启动幂等；结束时只有发生迁移或跳过才汇总一条 INFO，
无迁移无跳过完全不记日志（避免每次启动刷 WARNING）。

备份：生产调用点 bootstrap._build_storage 在 alembic 迁移前已写过
<DATA_DIR>/db_backup 快照，本模块不重复备份。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

# 复用 user_identity 的 identities.json 解析：两处格式判断不能各写一份、漂移。
from neobot_app.user_identity import _load_identity_index

#: 档案表里 key 就是本地 ID 的表。item_archive / bilibili_* 等表的 key 是业务
#: 数据（视频号、UID 等），不是本地 ID，不能改。
_ARCHIVE_KEY_KINDS = {
    "user_profile": "user",
    "user_summary": "user",
    "group_profile": "group",
    "group_summary": "group",
}
#: 自动总结计数器（archive_memories.table_name=memory_counter）的 key 形如
#: "group:<群ID>" / "private:<用户ID>"。
_COUNTER_TABLE = "memory_counter"
_COUNTER_KEY_KINDS = {"group": "group", "private": "user"}
#: 跨聊天会话的 kind → 本地 ID 类型；bilibili 等其它 kind 不动。
_SESSION_KINDS = {"group": "group", "private": "user"}


class _ConflictLog:
    """记录「目标 openid 行已存在」的跳过项：逐条 DEBUG，汇总由调用方记 INFO。"""

    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self.count = 0

    def record(self, table: str, legacy_id: str, openid: str, **extra: Any) -> None:
        self.count += 1
        self._logger.debug(
            "旧合成号迁移遇到已存在的 openid 行，跳过该条（保留旧数据不删除）",
            table=table,
            legacy_id=legacy_id,
            openid=openid,
            **extra,
        )


def _bump(counts: dict[str, int], table: str, count: int) -> None:
    if count:
        counts[table] = counts.get(table, 0) + count


def _exists(conn: sqlite3.Connection, table: str, **columns: Any) -> bool:
    clause = " AND ".join(f"{name}=?" for name in columns)
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {clause} LIMIT 1", tuple(columns.values())).fetchone()
    return row is not None


def _load_mapping_tables(conn: sqlite3.Connection, users: dict[str, str], groups: dict[str, str]) -> None:
    """把旧合成号→openid 装进两张临时表，供一次扫描的批量 UPDATE 使用。"""
    for name, mapping in (("legacy_user_ids", users), ("legacy_group_ids", groups)):
        conn.execute(f"CREATE TEMP TABLE {name} (legacy_id TEXT PRIMARY KEY, openid TEXT NOT NULL)")
        conn.executemany(f"INSERT INTO {name} VALUES (?, ?)", mapping.items())


def _migrate_bulk_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    mapping_table: str,
    counts: dict[str, int],
    *,
    fixed: dict[str, Any] | None = None,
) -> None:
    """改写没有唯一约束的表列：一条 UPDATE 扫一遍表，不按 ID 逐条扫描。"""
    extra = dict(fixed or {})
    prefix = "".join(f"{name}=? AND " for name in extra)
    sql = (
        f"UPDATE {table} SET {column} = "
        f"(SELECT openid FROM {mapping_table} WHERE legacy_id = {table}.{column}) "
        f"WHERE {prefix}{column} IN (SELECT legacy_id FROM {mapping_table})"
    )
    cursor = conn.execute(sql, tuple(extra.values()))
    _bump(counts, table, cursor.rowcount)


def _migrate_primary_key(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    mapping: dict[str, str],
    counts: dict[str, int],
    conflicts: _ConflictLog,
) -> None:
    """主键列改写：目标行已存在时跳过并记录（PK 冲突会直接失败）。"""
    migrated = 0
    for legacy_id, openid in mapping.items():
        if not _exists(conn, table, **{column: legacy_id}):
            continue
        if _exists(conn, table, **{column: openid}):
            conflicts.record(table, legacy_id, openid)
            continue
        conn.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (openid, legacy_id))
        migrated += 1
    _bump(counts, table, migrated)


def _migrate_archive_keys(
    conn: sqlite3.Connection,
    table: str,
    mapping: dict[str, dict[str, str]],
    counts: dict[str, int],
    conflicts: _ConflictLog,
    *,
    unique: bool,
) -> None:
    """档案表 key 改写；archive_memories 有 (table_name,key) 唯一约束，冲突要跳过。"""
    migrated = 0
    for table_name, kind in _ARCHIVE_KEY_KINDS.items():
        for legacy_id, openid in (mapping.get(kind) or {}).items():
            if not _exists(conn, table, table_name=table_name, key=legacy_id):
                continue
            if unique and _exists(conn, table, table_name=table_name, key=openid):
                conflicts.record(table, legacy_id, openid, table_name=table_name)
                continue
            conn.execute(
                f"UPDATE {table} SET key=? WHERE table_name=? AND key=?",
                (openid, table_name, legacy_id),
            )
            migrated += 1
    _bump(counts, table, migrated)


def _migrate_counter_keys(
    conn: sqlite3.Connection,
    mapping: dict[str, dict[str, str]],
    counts: dict[str, int],
    conflicts: _ConflictLog,
) -> None:
    """自动总结计数器的 "kind:<旧ID>" key 改写（唯一约束同 archive_memories）。"""
    keys = [row[0] for row in conn.execute("SELECT key FROM archive_memories WHERE table_name=?", (_COUNTER_TABLE,))]
    migrated = 0
    for legacy_key in keys:
        prefix, _, legacy_id = str(legacy_key).partition(":")
        kind = _COUNTER_KEY_KINDS.get(prefix)
        openid = (mapping.get(kind) or {}).get(legacy_id) if kind else None
        if not openid:
            continue
        new_key = f"{prefix}:{openid}"
        if _exists(conn, "archive_memories", table_name=_COUNTER_TABLE, key=new_key):
            conflicts.record("archive_memories", str(legacy_key), new_key, table_name=_COUNTER_TABLE)
            continue
        conn.execute(
            "UPDATE archive_memories SET key=? WHERE table_name=? AND key=?",
            (new_key, _COUNTER_TABLE, legacy_key),
        )
        migrated += 1
    _bump(counts, "archive_memories", migrated)


def _map_session_id(mapping: dict[str, dict[str, str]], kind: Any, local_id: Any) -> str:
    text = str(local_id)
    kind_name = _SESSION_KINDS.get(str(kind))
    return (mapping.get(kind_name) or {}).get(text, text) if kind_name else text


def _migrate_cross_chat_sessions(
    conn: sqlite3.Connection,
    mapping: dict[str, dict[str, str]],
    counts: dict[str, int],
    conflicts: _ConflictLog,
) -> None:
    """跨聊天会话两端 ID 改写；目标 (origin,target,boot) 已存在时跳过（有唯一约束）。"""
    rows = conn.execute(
        "SELECT id, origin_kind, origin_id, target_kind, target_id, boot_id FROM cross_chat_sessions"
    ).fetchall()
    migrated = 0
    for row_id, origin_kind, origin_id, target_kind, target_id, boot_id in rows:
        new_origin = _map_session_id(mapping, origin_kind, origin_id)
        new_target = _map_session_id(mapping, target_kind, target_id)
        if new_origin == origin_id and new_target == target_id:
            continue
        taken = conn.execute(
            "SELECT 1 FROM cross_chat_sessions WHERE origin_kind=? AND origin_id=? "
            "AND target_kind=? AND target_id=? AND boot_id=? AND id!=? LIMIT 1",
            (origin_kind, new_origin, target_kind, new_target, boot_id, row_id),
        ).fetchone()
        if taken is not None:
            conflicts.record(
                "cross_chat_sessions",
                f"{origin_kind}:{origin_id}->{target_kind}:{target_id}",
                f"{origin_kind}:{new_origin}->{target_kind}:{new_target}",
            )
            continue
        conn.execute(
            "UPDATE cross_chat_sessions SET origin_id=?, target_id=? WHERE id=?",
            (new_origin, new_target, row_id),
        )
        migrated += 1
    _bump(counts, "cross_chat_sessions", migrated)


def migrate_legacy_identity_ids(
    db_path: str | Path,
    data_dir: str | Path,
    *,
    logger: Logger | None = None,
) -> dict[str, int]:
    """把数据库里的旧合成号本地 ID 改写成 openid；返回各表改写条数。

    无 identities.json / 库文件 / 可迁移行时返回空表（no-op）。失败只记
    WARNING 不抛异常：迁移不是启动的硬依赖，旧数据在下次启动时会重试。
    """
    log = logger or NullLogger()
    mapping = _load_identity_index(Path(data_dir))
    users = mapping.get("user") or {}
    groups = mapping.get("group") or {}
    if not users and not groups:
        return {}
    path = Path(db_path)
    if not path.is_file():
        return {}

    counts: dict[str, int] = {}
    conflicts = _ConflictLog(log)
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            _load_mapping_tables(conn, users, groups)
            # 有唯一约束的表逐条迁移：先查再改，冲突跳过而不是删数据。
            _migrate_primary_key(conn, "user_data", "user_id", users, counts, conflicts)
            _migrate_primary_key(conn, "group_data", "group_id", groups, counts, conflicts)
            _migrate_archive_keys(conn, "archive_memories", mapping, counts, conflicts, unique=True)
            _migrate_counter_keys(conn, mapping, counts, conflicts)
            _migrate_cross_chat_sessions(conn, mapping, counts, conflicts)
            # 无唯一约束的表一条 UPDATE 扫一遍（messages 等表没有 ID 索引，
            # 按映射逐条 UPDATE 会反复全表扫描）。
            for mapping_table, conversation_kind in (
                ("legacy_user_ids", "private"),
                ("legacy_group_ids", "group"),
            ):
                for table in ("messages", "memories", "model_usage_records"):
                    _migrate_bulk_column(
                        conn,
                        table,
                        "conversation_id",
                        mapping_table,
                        counts,
                        fixed={"conversation_kind": conversation_kind},
                    )
            _migrate_bulk_column(conn, "messages", "sender_id", "legacy_user_ids", counts)
            _migrate_bulk_column(conn, "memories", "speaker_id", "legacy_user_ids", counts)
            _migrate_archive_keys(conn, "archive_snapshots", mapping, counts, conflicts, unique=False)
    except sqlite3.Error as exc:
        log.warning("旧合成号数据库迁移失败，旧数据保持原样", error=str(exc))
        return {}

    if counts or conflicts.count:
        fields: dict[str, Any] = {
            "migrated": sum(counts.values()),
            "skipped": conflicts.count,
        }
        if counts:
            fields["tables"] = counts
        log.info("旧合成号数据库迁移完成", **fields)
    return counts
