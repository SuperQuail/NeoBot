"""把 OneBot 数字 QQ号/群号与官方旧合成号的数据迁移到 openid。

官方通道早期用 13 位合成号当本地主键，OneBot 时代用真实 QQ号/群号；切到 openid 后
这些历史数据按新主键查不到。本模块把它们无损迁到 openid：

- 映射 = qqbot/identities.json（旧合成号 → openid）+ user_qq_map.json 中管理员写入
  的 trusted aliases（qq → openid）；只迁移有 openid 目标的映射。
- 核心库 data/neobot.db：资料行移动/合并、档案与自动总结计数器合并、档案快照与
  消息/记忆/用量/跨聊天会话的 ID 改写；official 模式（不含 dual）下改写定时任务
  绑定，避免 OneBot 仍在跑的混合部署被改坏。
- 迁移入口先给 agent 状态库与插件独立库各拍一份 sqlite online backup 快照
  （data/db_backup/identity_*.db，保留 5 份）；启动路径核心库已有 db_backup 快照，
  /linkqq、/linkgroup 触发的在线迁移由 IdentityMigrationCoordinator 额外补拍核心库。
- agent 状态库实际改写逻辑在 identity_agent_state_migration；插件库迁移在
  plugin_identity_migration，official_only 透传过去由插件模块门控：非 official 时
  跳过 group/会话类活跃绑定，只保留安全的用户级改写。

每个库独立单事务；会删除或覆盖旧行的操作先写 identity_migration_backup 备份行。
重复执行幂等；失败只记 WARNING 不阻断启动，下次启动或下次 link 会重试。
official 模式下迁移结束会 WARNING 列出缺少 openid 映射的定时任务/跨聊天会话，
提醒管理员先 /linkqq、/linkgroup 补齐映射。

shortcut: 映射只在启动/link 时读一次文件，运行中新增映射要等下一次触发；没有
openid 目标的未 link 用户数据保持原名，不做猜测性改写。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.bot_accounts import looks_like_real_group_number, looks_like_real_qq
from neobot_app.user_identity import _load_identity_index, _parse_alias_key
from .identity_migration_backup import agent_state_path, snapshot_migration_databases

_BACKUP_TABLE = "identity_migration_backup"
_BACKUP_DDL = (
    "CREATE TABLE IF NOT EXISTS identity_migration_backup ("
    "run_at TEXT NOT NULL, table_name TEXT NOT NULL, old_key TEXT NOT NULL, "
    "new_key TEXT NOT NULL, payload TEXT NOT NULL)"
)
#: 档案表 -> 主键类型；item_archive / bilibili_* 等业务表的 key 不是本地 ID，不动。
_ARCHIVE_KEY_KINDS = {
    "user_profile": "user", "user_summary": "user",
    "group_profile": "group", "group_summary": "group",
}
#: 自动总结计数器 key 形如 "group:<群ID>" / "private:<用户ID>"。
_COUNTER_TABLE = "memory_counter"
_COUNTER_KEY_KINDS = {"group": "group", "private": "user"}
#: 跨聊天会话 / 定时任务绑定里的 kind -> 本地 ID 类型；bilibili 等其它 kind 不动。
_SESSION_KINDS = {"group": "group", "private": "user"}
#: 资料行按字段类型取值；其余字段优先目标（openid）非空值，缺失取旧值。
_MAX_FIELDS = ("favorability", "avatar_fail_count")
_LATEST_FIELDS = ("fetched_at", "avatar_fetched_at")
_TEMP_USER_MAP = "identity_migration_users"
_TEMP_GROUP_MAP = "identity_migration_groups"
_TEMP_ANY_MAP = "identity_migration_any"
_PLUGINS_DATA = "plugins_data"
#: 未映射目标告警里最多列出的任务 ID 数，避免一条日志刷屏。
_UNMAPPED_REPORT_LIMIT = 20


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _merged_text(source: Any, target: Any) -> str:
    """旧（QQ号/合成号）版本在前、openid 版本在后，中间空行；一侧为空取另一侧。"""
    first, second = _text(source), _text(target)
    return f"{first}\n\n{second}" if first and second else first or second


def _latest(source: Any, target: Any) -> Any:
    if source in (None, ""):
        return target
    if target in (None, ""):
        return source
    return source if str(source) >= str(target) else target


def _json_dump(value: Any, *, sort_keys: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=sort_keys, default=str)


def _json_object(raw: Any) -> dict[str, Any]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _row_payload(row: sqlite3.Row) -> str:
    return _json_dump({name: row[name] for name in row.keys()})


def _load_tags(raw: Any) -> list[str]:
    """tags 列为 JSON 数组（新格式）或逗号分隔（旧格式）。"""
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        decoded = None
    if isinstance(decoded, list):
        return [str(tag) for tag in decoded]
    text = decoded if isinstance(decoded, str) else str(raw)
    return [part.replace(";", ",") for part in text.split(",") if part]


def _dump_tags(tags: Iterable[str]) -> str:
    return json.dumps(list(dict.fromkeys(tags)), ensure_ascii=True)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _fetch(conn: sqlite3.Connection, table: str, column: str, key: Any) -> sqlite3.Row | None:
    return conn.execute(f"SELECT * FROM {table} WHERE {column}=? LIMIT 1", (key,)).fetchone()


def _fetch_where(conn: sqlite3.Connection, table: str, **columns: Any) -> sqlite3.Row | None:
    clause = " AND ".join(f"{name}=?" for name in columns)
    return conn.execute(
        f"SELECT * FROM {table} WHERE {clause} LIMIT 1", tuple(columns.values())
    ).fetchone()


def _bump(counts: dict[str, int], table: str, count: int) -> None:
    if count:
        counts[table] = counts.get(table, 0) + int(count)


def _now_text() -> str:
    """与 SQLAlchemy 在 SQLite 里写的 DATETIME 文本格式保持可比（UTC）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ensure_backup(conn: sqlite3.Connection) -> None:
    conn.execute(_BACKUP_DDL)


def _backup(
    conn: sqlite3.Connection, run_at: str, table: str, old_key: Any, new_key: Any, payload: str
) -> None:
    conn.execute(
        f"INSERT INTO {_BACKUP_TABLE} VALUES (?, ?, ?, ?, ?)",
        (run_at, table, str(old_key), str(new_key), payload),
    )


# ── 映射装载 ─────────────────────────────────────────────────


class _Mappings:
    """旧 ID -> openid；users/groups 两个命名空间互不混用。"""

    def __init__(self) -> None:
        self.users: dict[str, str] = {}
        self.groups: dict[str, str] = {}

    def for_kind(self, kind: str) -> dict[str, str]:
        return self.groups if kind == "group" else self.users

    def __bool__(self) -> bool:
        return bool(self.users or self.groups)


def _load_mappings(data_dir: Path) -> _Mappings:
    index = _load_identity_index(data_dir)
    mappings = _Mappings()
    mappings.users.update(index.get("user") or {})
    mappings.groups.update(index.get("group") or {})
    try:
        raw = json.loads((data_dir / "user_qq_map.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return mappings
    aliases = raw.get("aliases") if isinstance(raw, dict) else None
    if not isinstance(aliases, dict):
        return mappings
    for key, entry in aliases.items():
        parsed = _parse_alias_key(str(key))
        if parsed is None:
            continue
        # 只有管理员命令写入的 trusted 映射才可信到可以搬数据；agent 工具写入的
        # 映射只影响展示，不能拿来合并账号（否则可能把两个不同的人合并）。
        if not isinstance(entry, dict) or not entry.get("trusted"):
            continue
        kind, _channel, local = parsed
        qq = _to_int(entry.get("qq"))
        if not qq:
            continue
        mapping = mappings.for_kind(kind)
        target = mapping.get(local, local)
        if not target or target == str(qq):
            continue
        # 本地 ID 仍是真实号规模 = 没有 openid 目标（未 link 的 OneBot 映射），跳过。
        real = looks_like_real_group_number if kind == "group" else looks_like_real_qq
        if real(target):
            continue
        mapping[str(qq)] = target
    return mappings


def official_only_mode(config: Any) -> bool:
    """只有 official（不含 dual）才改写后台绑定：OneBot 并存时旧号仍然有效。"""
    mode = str(getattr(getattr(config, "adapter", None), "mode", "") or "").strip().casefold()
    return mode == "official"


# ── 核心库：资料行 ───────────────────────────────────────────


def _merge_profile_row(source: sqlite3.Row, target: sqlite3.Row, pk: str) -> dict[str, Any]:
    """旧行 + 新行 -> 合并值：profile 旧在前，计数取大，时间取新，其余优先新值。"""
    merged: dict[str, Any] = {}
    for name in target.keys():
        if name == pk:
            continue
        old, new = source[name], target[name]
        if name == "profile":
            merged[name] = _merged_text(old, new)
        elif name in _MAX_FIELDS:
            merged[name] = max(_to_int(old), _to_int(new))
        elif name in _LATEST_FIELDS:
            merged[name] = _latest(old, new)
        else:
            merged[name] = new if new not in (None, "") else old
    return merged


def _migrate_profile_rows(
    conn: sqlite3.Connection, table: str, pk: str, mapping: dict[str, str],
    run_at: str, counts: dict[str, int],
) -> None:
    for old_key, new_key in mapping.items():
        if old_key == new_key:
            continue
        source = _fetch(conn, table, pk, old_key)
        if source is None:
            continue
        target = _fetch(conn, table, pk, new_key)
        if target is None:
            conn.execute(f"UPDATE {table} SET {pk}=? WHERE {pk}=?", (new_key, old_key))
        else:
            _backup(conn, run_at, table, old_key, new_key, _row_payload(source))
            merged = _merge_profile_row(source, target, pk)
            assignments = ", ".join(f"{name}=?" for name in merged)
            conn.execute(
                f"UPDATE {table} SET {assignments} WHERE {pk}=?", (*merged.values(), new_key)
            )
            conn.execute(f"DELETE FROM {table} WHERE {pk}=?", (old_key,))
        _bump(counts, table, 1)


# ── 核心库：档案 / 计数器 / 快照 ─────────────────────────────


def _archive_bump_assignments(columns: set[str], params: list[Any]) -> list[str]:
    """合并覆盖目标行时同步 version/updated_at，避免面板乐观锁与快照版本错位。"""
    assignments: list[str] = []
    if "version" in columns:
        assignments.append("version=version+1")
    if "updated_at" in columns:
        assignments.append("updated_at=?")
        params.append(_now_text())
    return assignments


def _migrate_archive_memories(
    conn: sqlite3.Connection, mappings: _Mappings, run_at: str, counts: dict[str, int]
) -> None:
    columns = _columns(conn, "archive_memories")
    for table_name, kind in _ARCHIVE_KEY_KINDS.items():
        for old_key, new_key in mappings.for_kind(kind).items():
            if old_key == new_key:
                continue
            source = _fetch_where(conn, "archive_memories", table_name=table_name, key=old_key)
            if source is None:
                continue
            target = _fetch_where(conn, "archive_memories", table_name=table_name, key=new_key)
            if target is None:
                conn.execute(
                    "UPDATE archive_memories SET key=? WHERE table_name=? AND key=?",
                    (new_key, table_name, old_key),
                )
            else:
                _backup(conn, run_at, "archive_memories", old_key, new_key, _row_payload(source))
                value = _merged_text(source["value"], target["value"])
                tags = _dump_tags([*_load_tags(source["tags"]), *_load_tags(target["tags"])])
                assignments = ["value=?", "tags=?"]
                params: list[Any] = [value, tags]
                assignments.extend(_archive_bump_assignments(columns, params))
                params.append(target["id"])
                conn.execute(
                    f"UPDATE archive_memories SET {', '.join(assignments)} WHERE id=?", params
                )
                conn.execute("DELETE FROM archive_memories WHERE id=?", (source["id"],))
            _bump(counts, "archive_memories", 1)


def _merge_counter_value(source: Any, target: Any) -> str:
    """计数器 JSON：count 相加，messages 拼接去重，其余字段目标优先。"""
    old, new = _json_object(source), _json_object(target)
    merged = dict(new)
    for name, value in old.items():
        merged.setdefault(name, value)
    merged["count"] = _to_int(old.get("count")) + _to_int(new.get("count"))
    messages: list[Any] = []
    seen: set[str] = set()
    for item in [*(old.get("messages") or []), *(new.get("messages") or [])]:
        token = _json_dump(item, sort_keys=True)
        if token not in seen:
            seen.add(token)
            messages.append(item)
    merged["messages"] = messages
    return _json_dump(merged)


def _migrate_counter_keys(
    conn: sqlite3.Connection, mappings: _Mappings, run_at: str, counts: dict[str, int]
) -> None:
    columns = _columns(conn, "archive_memories")
    rows = conn.execute(
        "SELECT * FROM archive_memories WHERE table_name=?", (_COUNTER_TABLE,)
    ).fetchall()
    for source in rows:
        prefix, _, local = str(source["key"]).partition(":")
        kind = _COUNTER_KEY_KINDS.get(prefix)
        new_key = mappings.for_kind(kind).get(local) if kind else None
        if not new_key or new_key == local:
            continue
        new_key = f"{prefix}:{new_key}"
        target = _fetch_where(conn, "archive_memories", table_name=_COUNTER_TABLE, key=new_key)
        if target is None:
            conn.execute("UPDATE archive_memories SET key=? WHERE id=?", (new_key, source["id"]))
        else:
            _backup(conn, run_at, "archive_memories", source["key"], new_key, _row_payload(source))
            value = _merge_counter_value(source["value"], target["value"])
            assignments = ["value=?"]
            params: list[Any] = [value]
            assignments.extend(_archive_bump_assignments(columns, params))
            params.append(target["id"])
            conn.execute(
                f"UPDATE archive_memories SET {', '.join(assignments)} WHERE id=?", params
            )
            conn.execute("DELETE FROM archive_memories WHERE id=?", (source["id"],))
        _bump(counts, "archive_memories", 1)


def _migrate_archive_snapshots(
    conn: sqlite3.Connection, mappings: _Mappings, counts: dict[str, int]
) -> None:
    """重键时把 snapshot.version 同步成目标档案行的当前 version（恢复用乐观锁）。"""
    snapshot_columns = _columns(conn, "archive_snapshots")
    sync_version = "version" in snapshot_columns and _table_exists(conn, "archive_memories")
    archive_has_version = "version" in _columns(conn, "archive_memories")
    for table_name, kind in _ARCHIVE_KEY_KINDS.items():
        for old_key, new_key in mappings.for_kind(kind).items():
            if old_key == new_key:
                continue
            assignments = ["key=?"]
            params: list[Any] = [new_key]
            if sync_version and archive_has_version:
                target = _fetch_where(
                    conn, "archive_memories", table_name=table_name, key=new_key
                )
                if target is not None:
                    assignments.append("version=?")
                    params.append(target["version"])
            params.extend((table_name, old_key))
            cursor = conn.execute(
                f"UPDATE archive_snapshots SET {', '.join(assignments)} "
                "WHERE table_name=? AND key=?",
                params,
            )
            _bump(counts, "archive_snapshots", cursor.rowcount)


# ── 核心库：消息 / 记忆 / 用量 / 跨聊天 / 定时任务 ───────────


def _load_temp_maps(conn: sqlite3.Connection, mappings: _Mappings) -> None:
    for name, mapping in (
        (_TEMP_USER_MAP, mappings.users),
        (_TEMP_GROUP_MAP, mappings.groups),
        (_TEMP_ANY_MAP, {**mappings.users, **mappings.groups}),
    ):
        conn.execute(
            f"CREATE TEMP TABLE IF NOT EXISTS {name} "
            "(legacy_id TEXT PRIMARY KEY, openid TEXT NOT NULL)"
        )
        conn.executemany(f"INSERT OR REPLACE INTO {name} VALUES (?, ?)", mapping.items())


def _bulk_update_column(
    conn: sqlite3.Connection, table: str, column: str, map_table: str,
    counts: dict[str, int], *, fixed: dict[str, Any] | None = None,
) -> None:
    if not _table_exists(conn, table):
        return
    extra = dict(fixed or {})
    prefix = "".join(f"{name}=? AND " for name in extra)
    sql = (
        f"UPDATE {table} SET {column} = (SELECT openid FROM {map_table} "
        f"WHERE legacy_id = {table}.{column}) WHERE {prefix}"
        f"{column} IN (SELECT legacy_id FROM {map_table})"
    )
    _bump(counts, table, conn.execute(sql, tuple(extra.values())).rowcount)


def _migrate_conversation_columns(conn: sqlite3.Connection, counts: dict[str, int]) -> None:
    for map_table, conversation_kind in ((_TEMP_USER_MAP, "private"), (_TEMP_GROUP_MAP, "group")):
        for table in ("messages", "memories"):
            _bulk_update_column(
                conn, table, "conversation_id", map_table, counts,
                fixed={"conversation_kind": conversation_kind},
            )
    _bulk_update_column(conn, "messages", "sender_id", _TEMP_USER_MAP, counts)
    _bulk_update_column(conn, "memories", "speaker_id", _TEMP_USER_MAP, counts)
    # model_usage_records 可能有 conversation_kind：同号用户/群必须按 kind 各用各的映射，
    # 混用会把 private 行写成群 openid；没有该列（老库）才退回合并映射。
    if "conversation_kind" in _columns(conn, "model_usage_records"):
        for map_table, conversation_kind in (
            (_TEMP_USER_MAP, "private"),
            (_TEMP_GROUP_MAP, "group"),
        ):
            _bulk_update_column(
                conn, "model_usage_records", "conversation_id", map_table, counts,
                fixed={"conversation_kind": conversation_kind},
            )
    else:
        _bulk_update_column(
            conn, "model_usage_records", "conversation_id", _TEMP_ANY_MAP, counts
        )


def _map_session_id(mappings: _Mappings, kind: Any, local_id: Any) -> str:
    text = str(local_id)
    target_kind = _SESSION_KINDS.get(str(kind))
    return mappings.for_kind(target_kind).get(text, text) if target_kind else text


def _migrate_cross_chat_sessions(
    conn: sqlite3.Connection,
    mappings: _Mappings,
    counts: dict[str, int],
    log: Logger,
    *,
    warn_unmapped: bool,
) -> None:
    rows = conn.execute(
        "SELECT id, origin_kind, origin_id, target_kind, target_id, boot_id "
        "FROM cross_chat_sessions"
    ).fetchall()
    unmapped_rows: set[Any] = set()
    unmapped_ends = 0
    examples: list[str] = []
    for row in rows:
        if warn_unmapped:
            for kind, local in (
                (row["origin_kind"], row["origin_id"]),
                (row["target_kind"], row["target_id"]),
            ):
                target_kind = _SESSION_KINDS.get(str(kind))
                text = str(local or "")
                if target_kind and text.isdigit() and text not in mappings.for_kind(target_kind):
                    unmapped_rows.add(row["id"])
                    unmapped_ends += 1
                    if len(examples) < 10:
                        examples.append(f"{kind}:{text}")
        new_origin = _map_session_id(mappings, row["origin_kind"], row["origin_id"])
        new_target = _map_session_id(mappings, row["target_kind"], row["target_id"])
        if new_origin == row["origin_id"] and new_target == row["target_id"]:
            continue
        taken = conn.execute(
            "SELECT 1 FROM cross_chat_sessions WHERE origin_kind=? AND origin_id=? "
            "AND target_kind=? AND target_id=? AND boot_id=? AND id!=? LIMIT 1",
            (row["origin_kind"], new_origin, row["target_kind"], new_target,
             row["boot_id"], row["id"]),
        ).fetchone()
        if taken is not None:
            log.debug(
                "跨聊天会话目标已存在，保留原行",
                origin_id=str(row["origin_id"]), target_id=str(row["target_id"]),
            )
            continue
        conn.execute(
            "UPDATE cross_chat_sessions SET origin_id=?, target_id=? WHERE id=?",
            (new_origin, new_target, row["id"]),
        )
        _bump(counts, "cross_chat_sessions", 1)
    if unmapped_rows:
        log.warning(
            "official 模式下仍有跨聊天会话缺少 openid 映射，后台回复/通知将匹配不到官方会话",
            sessions=len(unmapped_rows),
            ends=unmapped_ends,
            examples=examples,
        )


def _binding_items(raw: Any) -> list[Any] | None:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _rewrite_bindings(raw: Any, mappings: _Mappings) -> tuple[str, bool]:
    data = _binding_items(raw)
    if data is None:
        return str(raw or "[]"), False
    changed = False
    result: list[Any] = []
    for item in data:
        if isinstance(item, dict):
            kind = str(item.get("kind") or "")
            local_id = str(item.get("id") or "")
            target_kind = _SESSION_KINDS.get(kind)
            new_id = mappings.for_kind(target_kind).get(local_id) if target_kind else None
            if new_id and new_id != local_id:
                item = {**item, "id": new_id}
                changed = True
        result.append(item)
    if not changed:
        return str(raw or "[]"), False
    return _json_dump(result, sort_keys=True), True


def _rewrite_archived_payload(raw: Any, mappings: _Mappings) -> tuple[str, bool]:
    payload = _json_object(raw)
    if not payload:
        return str(raw or "{}"), False
    rewritten, changed = _rewrite_bindings(_json_dump(payload.get("bindings") or []), mappings)
    if not changed:
        return str(raw or "{}"), False
    payload["bindings"] = json.loads(rewritten)
    return _json_dump(payload, sort_keys=True), True


def _report_unmapped_scheduled(
    conn: sqlite3.Connection, mappings: _Mappings, log: Logger
) -> None:
    """official 下数字绑定且无映射 = 到点匹配不到官方会话；迁移后必须留下可查告警。"""
    if not _table_exists(conn, "scheduled_tasks"):
        return
    rows = conn.execute(
        "SELECT task_uuid, bindings_json FROM scheduled_tasks WHERE state='active'"
    ).fetchall()
    task_ids: set[str] = set()
    unmapped = 0
    for row in rows:
        for item in _binding_items(row["bindings_json"]) or []:
            if not isinstance(item, dict):
                continue
            target_kind = _SESSION_KINDS.get(str(item.get("kind") or ""))
            local = str(item.get("id") or "")
            if not target_kind or not local.isdigit():
                continue
            if local in mappings.for_kind(target_kind):
                continue
            unmapped += 1
            task_ids.add(str(row["task_uuid"]))
    if not unmapped:
        return
    log.warning(
        "official 模式下仍有定时任务绑定缺少 openid 映射，将匹配不到官方会话",
        tasks=len(task_ids),
        bindings=unmapped,
        task_uuids=sorted(task_ids)[:_UNMAPPED_REPORT_LIMIT],
        task_uuid_total=len(task_ids),
        hint="先 /linkqq、/linkgroup 建立映射，再重启或再次 link 触发的迁移会增量改写",
    )


def _migrate_scheduled(
    conn: sqlite3.Connection, mappings: _Mappings, counts: dict[str, int], log: Logger
) -> None:
    for table, columns in (
        ("scheduled_tasks", ("bindings_json",)),
        ("completed_scheduled_tasks", ("bindings_json", "archived_payload_json")),
    ):
        if not _table_exists(conn, table):
            continue
        rows = conn.execute(f"SELECT id, {', '.join(columns)} FROM {table}").fetchall()
        for row in rows:
            values: dict[str, str] = {}
            for column in columns:
                if column == "archived_payload_json":
                    value, changed = _rewrite_archived_payload(row[column], mappings)
                else:
                    value, changed = _rewrite_bindings(row[column], mappings)
                if changed:
                    values[column] = value
            if not values:
                continue
            assignments = ", ".join(f"{column}=?" for column in values)
            conn.execute(
                f"UPDATE {table} SET {assignments} WHERE id=?", (*values.values(), row["id"])
            )
            _bump(counts, table, 1)
    _report_unmapped_scheduled(conn, mappings, log)


# ── 单库事务 ─────────────────────────────────────────────────


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _migrate_core_db(
    db_path: Path, mappings: _Mappings, *, official_only: bool, run_at: str, log: Logger
) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not db_path.is_file():
        return counts
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        with conn:
            _ensure_backup(conn)
            _load_temp_maps(conn, mappings)
            for table, pk, mapping in (
                ("user_data", "user_id", mappings.users),
                ("group_data", "group_id", mappings.groups),
            ):
                if _table_exists(conn, table):
                    _migrate_profile_rows(conn, table, pk, mapping, run_at, counts)
            if _table_exists(conn, "archive_memories"):
                _migrate_archive_memories(conn, mappings, run_at, counts)
                if official_only:
                    # 计数器是会话级数据：dual/onebot 仍使用数字 ID，不能改写。
                    _migrate_counter_keys(conn, mappings, run_at, counts)
            if _table_exists(conn, "archive_snapshots"):
                _migrate_archive_snapshots(conn, mappings, counts)
            if official_only:
                # 消息/记忆/用量/跨聊天/定时任务绑定都是会话级数据：只有官方单通道才改写，
                # dual/onebot 下改写会让 OneBot 历史与任务目标断档。
                _migrate_conversation_columns(conn, counts)
                if _table_exists(conn, "cross_chat_sessions"):
                    _migrate_cross_chat_sessions(
                        conn, mappings, counts, log, warn_unmapped=True
                    )
                _migrate_scheduled(conn, mappings, counts, log)
    except Exception as exc:  # 迁移是 best-effort：任何解析/DB 异常都不能阻断启动
        log.warning("身份数据迁移失败，核心库保持原样", path=str(db_path), error=str(exc))
        return {}
    finally:
        if conn is not None:
            conn.close()
    return counts


# ── 对外入口 + link 后即时迁移 ───────────────────────────────


def migrate_identity_data(
    db_path: str | Path,
    data_dir: str | Path,
    *,
    official_only: bool = False,
    backup_aux: bool = True,
    logger: Logger | None = None,
) -> dict[str, int]:
    """把旧合成号/QQ号数据迁到 openid；返回各表迁移计数（无迁移返回空 dict）。

    两个库各自单事务；任一库失败只记 WARNING 不抛异常，另一个库继续。
    无映射文件时完全 no-op（不建备份表、不拍快照、不记日志）。
    backup_aux=False 供在线迁移协调器使用（它已先给全部库拍过快照）。
    """
    log = logger or NullLogger()
    data_path = Path(data_dir)
    mappings = _load_mappings(data_path)
    if not mappings:
        return {}
    if backup_aux:
        snapshot_migration_databases(Path(db_path), data_path, include_core=False, log=log)
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # 延迟导入：agent 迁移复用本模块工具函数，顶层互相 import 会成环。
    from neobot_app.database.identity_agent_state_migration import migrate_agent_state_db

    counts: dict[str, int] = {}
    for migrated in (
        _migrate_core_db(
            Path(db_path), mappings, official_only=official_only, run_at=run_at, log=log
        ),
        migrate_agent_state_db(
            agent_state_path(data_path), mappings, run_at=run_at, log=log
        ),
    ):
        for table, count in migrated.items():
            _bump(counts, table, count)
    # 插件独立库：official_only 透传给插件迁移模块——非 official（dual/OneBot）时
    # 它自行跳过群/会话绑定（streaming_parser 整库跳过），只保留安全的用户级改写。
    plugins_root = data_path / _PLUGINS_DATA
    plugin_counts: dict[str, dict[str, int]] = {}
    try:
        from neobot_app.database.plugin_identity_migration import migrate_plugin_databases

        plugin_counts = migrate_plugin_databases(
            plugins_root,
            user_map=mappings.users,
            group_map=mappings.groups,
            official_only=official_only,
            logger=log,
        )
    except Exception as exc:  # 防御性兜底：插件迁移失败不阻断核心迁移
        log.warning("插件库身份迁移失败，插件数据保持原样", error=str(exc))
    for plugin_name, tables in (plugin_counts or {}).items():
        for table, count in (tables or {}).items():
            _bump(counts, f"plugin:{plugin_name}:{table}", count)
    if counts:
        log.info("身份数据迁移完成", migrated=sum(counts.values()), tables=counts)
    return counts


class IdentityMigrationCoordinator:
    """link 成功后的即时迁移入口；bootstrap 装配时绑定，测试/未装配时为 None。"""

    def __init__(
        self,
        *,
        db_path: str | Path,
        data_dir: str | Path,
        official_only: bool = False,
        logger: Logger | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._data_dir = Path(data_dir)
        self._official_only = bool(official_only)
        self._logger = logger or NullLogger()

    def _snapshot_before_migration(self) -> None:
        """在线迁移没有启动快照可用：先给核心库 + agent/插件库各拍一份。"""
        snapshot_migration_databases(
            self._db_path, self._data_dir, include_core=True, log=self._logger
        )

    async def run(self) -> dict[str, int]:
        """在线程池里跑同步迁移：不阻塞事件循环，也绝不把 link 命令顶掉。"""
        try:
            await asyncio.to_thread(self._snapshot_before_migration)
            return await asyncio.to_thread(
                migrate_identity_data,
                self._db_path,
                self._data_dir,
                official_only=self._official_only,
                backup_aux=False,
                logger=self._logger,
            )
        except Exception as exc:  # 迁移是 best-effort，失败只记日志
            self._logger.warning("link 后的身份数据迁移失败，旧数据保持不变", error=str(exc))
            return {}


_coordinator: IdentityMigrationCoordinator | None = None


def bind_identity_migration(coordinator: IdentityMigrationCoordinator | None) -> None:
    global _coordinator
    _coordinator = coordinator


def get_identity_migration() -> IdentityMigrationCoordinator | None:
    return _coordinator
