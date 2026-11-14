"""a10 → a11：自动修复错误的 OneBot→openid 身份迁移（能恢复的就恢复）。

用法（生产设备先停 bot）：
    python scripts/repair_identity_migration.py --data-dir app/data --dry-run
    python scripts/repair_identity_migration.py --data-dir app/data --apply

恢复原则：
- 找到**迁移前**核心库快照（db_backup 里没有 identity_migration_backup 表的最近 neobot_*.db）。
- 对映射涉及的用户/群，把快照里的资料行、档案行、计数器写回当前库（覆盖错误合并结果）。
- 对 messages/memories/model_usage/cross_chat/archive_snapshots/scheduled_tasks：
  按快照行把被改写的身份列还原（只还原落在错误映射 openid 上的行），快照之后的新行不动。
- agent 状态库与插件库：用迁移前 identity_* 快照整库恢复（先备份当前库）。
- 没有可用快照时：只回填 identity_migration_backup 里保存的源行，并在输出里明确说明无法恢复的部分。
所有写操作前先把当前库复制到 data/db_backup/pre-repair-<时间>/。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIGRATION_TABLE = "identity_migration_backup"
#: 默认只修个人档案：群档案用户明确说没问题，不动。
PROFILE_TABLES = {"user_data": "user_id"}
ARCHIVE_TABLES = {"user_profile": "user", "user_summary": "user"}
ID_COLUMNS = {
    "messages": ("event_id", ("conversation_id", "sender_id")),
    "memories": ("id", ("conversation_id", "speaker_id")),
    "model_usage_records": ("id", ("conversation_id",)),
    "cross_chat_sessions": ("id", ("origin_id", "target_id")),
    "archive_snapshots": ("id", ("key",)),
}


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _load_mappings(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    users: dict[str, str] = {}
    groups: dict[str, str] = {}
    qqbot = data_dir / "qqbot" / "identities.json"
    if qqbot.is_file():
        try:
            raw = json.loads(qqbot.read_text(encoding="utf-8"))
            for openid, legacy in (raw.get("users") or {}).items():
                users[str(legacy)] = str(openid)
            for openid, legacy in (raw.get("groups") or {}).items():
                groups[str(legacy)] = str(openid)
        except (OSError, ValueError):
            pass
    mapping = data_dir / "user_qq_map.json"
    if mapping.is_file():
        try:
            raw = json.loads(mapping.read_text(encoding="utf-8"))
            for key, entry in (raw.get("aliases") or {}).items():
                parts = str(key).split(":")
                if len(parts) != 3 or not isinstance(entry, dict):
                    continue
                kind, _channel, local = parts
                qq = str(entry.get("qq") or "").strip()
                if not qq:
                    continue
                target = users.get(local, local) if kind == "user" else groups.get(local, local)
                (users if kind == "user" else groups)[qq] = target
        except (OSError, ValueError):
            pass
    return users, groups


def _find_core_snapshot(backup_dir: Path) -> Path | None:
    """最近一份「没有 identity_migration_backup 表」的 neobot 快照 = 迁移前。"""
    if not backup_dir.is_dir():
        return None
    for path in sorted(backup_dir.glob("neobot_*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            conn = _connect(path)
            try:
                if not _has_table(conn, MIGRATION_TABLE):
                    return path
            finally:
                conn.close()
        except sqlite3.Error:
            continue
    return None


def _find_latest(backup_dir: Path, pattern: str) -> Path | None:
    files = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _backup_payload(conn: sqlite3.Connection, old_key: str, new_key: str) -> dict[str, Any] | None:
    if not _has_table(conn, MIGRATION_TABLE):
        return None
    row = conn.execute(
        f"SELECT payload FROM {MIGRATION_TABLE} WHERE old_key=? AND new_key=? LIMIT 1",
        (str(old_key), str(new_key)),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"])
        return payload if isinstance(payload, dict) else None
    except (TypeError, ValueError):
        return None


def _restore_profile_tables(cur: sqlite3.Connection, snap: sqlite3.Connection, mappings: dict[str, str]) -> int:
    changed = 0
    for table, pk in PROFILE_TABLES.items():
        if not (_has_table(cur, table) and _has_table(snap, table)):
            continue
        cols = _cols(snap, table)
        for old, new in mappings.items():
            for key in {str(old), str(new)}:
                row = snap.execute(f"SELECT * FROM {table} WHERE {pk}=?", (key,)).fetchone()
                if row is None:
                    continue
                values = [row[col] for col in cols]
                cur.execute(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", values)
                changed += 1
    return changed


def _restore_archives(cur: sqlite3.Connection, snap: sqlite3.Connection, users: dict[str, str], groups: dict[str, str]) -> int:
    changed = 0
    if not (_has_table(cur, "archive_memories") and _has_table(snap, "archive_memories")):
        return 0
    cols = _cols(snap, "archive_memories")
    for table in ARCHIVE_TABLES:
        source = users if ARCHIVE_TABLES[table] == "user" else groups
        keys = set()
        for old, new in source.items():
            keys.update({str(old), str(new)})
        if table == "memory_counter":
            keys = {f"private:{key}" for key in keys}
        for key in keys:
            rows = snap.execute("SELECT * FROM archive_memories WHERE table_name=? AND key=?", (table, key)).fetchall()
            cur.execute("DELETE FROM archive_memories WHERE table_name=? AND key=?", (table, key))
            for row in rows:
                cur.execute(
                    f"INSERT INTO archive_memories ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [row[col] for col in cols],
                )
                changed += 1
    return changed


def _restore_id_columns(cur: sqlite3.Connection, snap: sqlite3.Connection, affected_new: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, (pk, columns) in ID_COLUMNS.items():
        if not (_has_table(cur, table) and _has_table(snap, table)):
            continue
        snap_cols = _cols(snap, table)
        count = 0
        for row in snap.execute(f"SELECT * FROM {table}").fetchall():
            current = cur.execute(f"SELECT * FROM {table} WHERE {pk}=?", (row[pk],)).fetchone()
            if current is None:
                cur.execute(
                    f"INSERT OR IGNORE INTO {table} ({','.join(snap_cols)}) VALUES ({','.join('?' * len(snap_cols))})",
                    [row[col] for col in snap_cols],
                )
                count += 1
                continue
            values = {}
            for column in columns:
                if column not in snap_cols:
                    continue
                if str(current[column]) != str(row[column]) and str(current[column]) in affected_new:
                    values[column] = row[column]
            if values:
                assignments = ", ".join(f"{column}=?" for column in values)
                cur.execute(f"UPDATE {table} SET {assignments} WHERE {pk}=?", (*values.values(), row[pk]))
                count += 1
        counts[table] = count
    return counts


def _restore_scheduled(cur: sqlite3.Connection, snap: sqlite3.Connection, affected_new: set[str]) -> int:
    count = 0
    for table, column in (("scheduled_tasks", "bindings_json"), ("completed_scheduled_tasks", "bindings_json"), ("completed_scheduled_tasks", "archived_payload_json")):
        if not (_has_table(cur, table) and _has_table(snap, table)):
            continue
        for row in snap.execute(f"SELECT id, {column} FROM {table}").fetchall():
            current = cur.execute(f"SELECT {column} FROM {table} WHERE id=?", (row["id"],)).fetchone()
            if current is None:
                continue
            text = str(current[column] or "")
            if not any(value and value in text for value in affected_new):
                continue
            cur.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (row[column], row["id"]))
            count += 1
    return count


def _restore_payloads(cur: sqlite3.Connection) -> int:
    if not _has_table(cur, MIGRATION_TABLE):
        return 0
    count = 0
    for row in cur.execute(f"SELECT table_name, old_key, new_key, payload FROM {MIGRATION_TABLE}").fetchall():
        table = str(row["table_name"])
        if table not in {"user_data", "group_data", "archive_memories"} or not _has_table(cur, table):
            continue
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        cols = [col for col in _cols(cur, table) if col in payload]
        if not cols:
            continue
        cur.execute(
            f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [payload[col] for col in cols],
        )
        count += 1
    return count


def repair(data_dir: Path, apply: bool, *, include_history: bool = False, include_plugins: bool = False) -> dict[str, Any]:
    backup_dir = data_dir / "db_backup"
    core = data_dir / "neobot.db"
    agent = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
    plugin_dbs = sorted(data_dir.glob("plugins_data/*/databases/*.db"))
    core_snap = _find_core_snapshot(backup_dir)
    agent_snap = _find_latest(backup_dir, "identity_agent_state_*.db")
    plugin_snaps = {
        db.parent.parent.name: _find_latest(backup_dir, f"identity_{db.parent.parent.name}_*.db")
        for db in plugin_dbs
    }
    users, groups = _load_mappings(data_dir)
    affected_new = set(users.values()) | set(groups.values())
    result: dict[str, Any] = {"core_snapshot": str(core_snap) if core_snap else None, "agent_snapshot": str(agent_snap) if agent_snap else None, "plugins": {k: (str(v) if v else None) for k, v in plugin_snaps.items()}, "mappings": {"users": len(users), "groups": len(groups)}, "applied": False}
    if not core_snap:
        result["note"] = "没有迁移前核心库快照；只能回填 identity_migration_backup 源行，消息/记忆等纯 ID 改写无法完整恢复"
    if apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safety = backup_dir / f"pre-repair_{stamp}"
        safety.mkdir(parents=True, exist_ok=True)
        for path in [core, agent, *plugin_dbs]:
            if path.is_file():
                _backup(path, safety / path.name)
        result["safety_backup"] = str(safety)
    if core_snap:
        snap = _connect(core_snap)
        cur = _connect(core)
        try:
            if apply:
                with cur:
                    result["profiles"] = _restore_profile_tables(cur, snap, users)
                    result["archives"] = _restore_archives(cur, snap, users, {})
                    if include_history:
                        result["ids"] = _restore_id_columns(cur, snap, affected_new)
                        result["scheduled"] = _restore_scheduled(cur, snap, affected_new)
        finally:
            snap.close()
            cur.close()
    if apply:
        cur = _connect(core)
        try:
            with cur:
                result["payload_rows"] = _restore_payloads(cur)
        finally:
            cur.close()
        restore_dbs = [(agent, agent_snap)] if include_plugins else []
        restore_dbs += [(db, plugin_snaps.get(db.parent.parent.name)) for db in plugin_dbs] if include_plugins else []
        for path, snapshot in restore_dbs:
            if path.is_file() and snapshot and snapshot.is_file():
                _backup(snapshot, path)
                result.setdefault("restored_databases", []).append(str(path))
    result["applied"] = apply
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自动修复错误的身份迁移（a10→a11）")
    parser.add_argument("--data-dir", default="app/data")
    parser.add_argument("--apply", action="store_true", help="真正写库；默认只打印计划")
    parser.add_argument("--dry-run", action="store_true", help="显式只预览，不写库（默认行为）")
    parser.add_argument("--include-history", action="store_true", help="额外恢复消息/记忆等 ID（默认只修个人档案）")
    parser.add_argument("--include-plugins", action="store_true", help="额外恢复 agent/插件库（默认不动）")
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    if not (data_dir / "neobot.db").is_file():
        print(f"找不到 {data_dir / 'neobot.db'}", file=sys.stderr)
        return 2
    result = repair(
        data_dir,
        bool(args.apply and not args.dry_run),
        include_history=bool(args.include_history),
        include_plugins=bool(args.include_plugins),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _has_duplicate_targets(data_dir: Path) -> bool:
    """a10 错误迁移的典型特征：多个旧 ID 被映射到同一个 openid。"""
    users, groups = _load_mappings(data_dir)
    for mapping in (users, groups):
        targets = [str(value) for value in mapping.values()]
        if len(targets) != len(set(targets)):
            return True
    return False


def auto_repair_if_needed(data_dir: Path, logger=None) -> bool:
    """a10→a11 启动时自动修复个人档案；只执行一次。

    触发条件：映射文件里出现“多个旧 ID → 同一 openid”（a10 @ 目标 bug 的典型结果），
    且 db_backup 里仍有迁移前快照。群档案按用户要求不动。
    """
    marker = data_dir / ".neobot" / "identity_repair_a11.done"
    if marker.exists():
        return False
    if not _has_duplicate_targets(data_dir):
        return False
    if _find_core_snapshot(data_dir / "db_backup") is None:
        if logger is not None:
            logger.warning("检测到重复 openid 映射，但没有迁移前快照，跳过自动修复")
        return False
    result = repair(data_dir, True)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"repaired_at": datetime.now(timezone.utc).isoformat(), "result": result}, ensure_ascii=False), encoding="utf-8")
    if logger is not None:
        logger.warning("检测到 a10 错误身份映射，已自动恢复个人档案", result=result)
    return True


def _clear_aliases(data_dir: Path, safety_dir: Path, logger=None) -> int:
    """放弃 a10 期间写入的全部人工映射：备份后清空 aliases，保留 identities.json。"""
    path = data_dir / "user_qq_map.json"
    if not path.is_file():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    aliases = raw.get("aliases") if isinstance(raw, dict) else None
    if not isinstance(aliases, dict) or not aliases:
        return 0
    safety_dir.mkdir(parents=True, exist_ok=True)
    (safety_dir / "user_qq_map.a10.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    raw["aliases"] = {}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    if logger is not None:
        logger.warning("已放弃 a10 人工身份映射（已备份）", removed=len(aliases))
    return len(aliases)


def auto_rebuild_if_a10_migration(
    data_dir: Path, logger=None, *, apply: bool = True, force: bool = False
) -> bool:
    """a10→a11：默认放弃 a10 映射，整体回滚到迁移前快照，再让 a11 重建。

    触发：当前核心库存在 identity_migration_backup 表（说明 a10 迁移跑过）。
    动作（stop-the-world，必须在 bot 启动早期、alembic 之前调用）：
    - 备份当前 core/agent/插件库；
    - 恢复 a10 迁移前 core/agent/插件快照；
    - 清空 user_qq_map aliases（备份）；
    - 写 marker，后续 a11 迁移只用 identities.json 的合成号映射重建。
    失败只 WARNING，不阻断启动。
    """
    marker = data_dir / ".neobot" / "identity_rebuild_a11.done"
    if marker.exists() and not force:
        return False
    core = data_dir / "neobot.db"
    if not core.is_file():
        return False
    try:
        conn = _connect(core)
        try:
            migrated = _has_table(conn, MIGRATION_TABLE)
        finally:
            conn.close()
        if not migrated:
            return False
        core_snap = _find_core_snapshot(data_dir / "db_backup")
        if core_snap is None:
            if logger is not None:
                logger.warning("检测到 a10 迁移，但没有迁移前快照；无法整体回滚")
            return False
        if not apply:
            if logger is not None:
                logger.warning("检测到 a10 迁移，dry-run 将回滚到快照", snapshot=str(core_snap))
            return True
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safety = data_dir / "db_backup" / f"pre-rebuild_{stamp}"
        safety.mkdir(parents=True, exist_ok=True)
        agent = data_dir / "agent_tools" / "state" / "agent_state.sqlite3"
        plugin_dbs = sorted(data_dir.glob("plugins_data/*/databases/*.db"))
        for path in [core, agent, *plugin_dbs]:
            if path.is_file():
                _backup(path, safety / (path.parent.parent.name + "_" + path.name if path.name.startswith("agent") is False else path.name))
        _backup(core_snap, core)
        agent_snap = _find_latest(data_dir / "db_backup", "identity_agent_state_*.db")
        if agent.is_file() and agent_snap is not None:
            _backup(agent_snap, agent)
        for db in plugin_dbs:
            snap = _find_latest(data_dir / "db_backup", f"identity_{db.parent.parent.name}_*.db")
            if snap is not None:
                _backup(snap, db)
        removed = _clear_aliases(data_dir, safety, logger)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"rebuilt_at": datetime.now(timezone.utc).isoformat(), "snapshot": str(core_snap), "removed_aliases": removed}, ensure_ascii=False), encoding="utf-8")
        if logger is not None:
            logger.warning("已整体回滚 a10 身份迁移，等待 a11 重建", snapshot=str(core_snap), removed_aliases=removed)
        return True
    except Exception as exc:  # 迁移失败不能阻断启动
        if logger is not None:
            logger.warning("a10→a11 整体回滚失败，保持现状启动", error=str(exc))
        return False
