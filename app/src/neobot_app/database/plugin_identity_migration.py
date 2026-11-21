"""内置插件独立库与配置文件：旧数字 ID → 官方 openid 迁移。

插件库（``plugins_data/<插件>/databases/*.db``）是独立 SQLite，本体启动迁移覆盖
不到；speaking_schedule 的身份写在配置文件里（``config.toml`` 的
``overrides[].id``、``mutes.json`` 的 ``group:<id>``/``private:<id>`` scope）。
官方通道按 openid 查旧数字 ID 的订阅/积分/签到/作息配置会全部落空，本模块逐库单
事务、逐文件备份后原子替换：

- 有唯一约束、目标行已存在的表合并旧行（规则见各迁移函数），合并或删除前把整行
  JSON 写进 ``identity_migration_backup``；没有唯一约束的列直接 ``UPDATE``；
- 每张表用 savepoint 隔离：缺表/缺列只跳过该表，不拖累已改好的其它表；
- ``official_only`` 为假（dual/OneBot 模式）时不动群/会话绑定：streaming_parser
  整个库跳过，minigame 只迁用户级列，speaking_schedule 文件整个跳过——混合部署下
  OneBot 仍按真实群号使用这些活跃绑定，改了就查不到。

重复执行幂等；单库/单文件失败只记 WARNING 不抛——插件数据不是启动硬依赖，下次
启动会重试。调用方是 ``neobot_app.database.identity_data_migration`` 的入口，映射
由 identities.json + user_qq_map.json 构造后传入；本模块不读映射文件。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tomlkit

from neobot_contracts.ports.logging import Logger, NullLogger

#: 插件库相对 plugins_data 的路径（存在才处理）。
_DATABASES = (
    ("streaming_parser", "streaming_parser/databases/streaming_parser.db"),
    ("minigame", "minigame/databases/minigame.db"),
    ("starship", "starship/databases/starship.db"),
)

#: 没有 SQLite、身份写在配置文件里的插件。
_SPEAKING_SCHEDULE = "speaking_schedule"
_SPEAKING_CONFIG = "config.toml"
_SPEAKING_MUTES = "mutes.json"

_BACKUP_TABLE = "identity_migration_backup"
_BACKUP_DDL = f"""
CREATE TABLE IF NOT EXISTS {_BACKUP_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    table_name TEXT NOT NULL,
    old_key TEXT NOT NULL,
    new_key TEXT NOT NULL,
    payload TEXT NOT NULL
)
"""

_Migrator = Callable[
    [sqlite3.Connection, dict[str, str], dict[str, str], str, dict[str, int], Logger, bool],
    None,
]


def _bump(counts: dict[str, int], table: str, count: int) -> None:
    if count:
        counts[table] = counts.get(table, 0) + count


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _legacy_ids(conn: sqlite3.Connection, table: str, column: str, mapping: dict[str, str]) -> list[tuple[str, str]]:
    """表里实际存在、且有映射的旧 ID → openid；已是 openid / 无映射的原样跳过。"""
    pairs: list[tuple[str, str]] = []
    for (value,) in conn.execute(f"SELECT DISTINCT {column} FROM {table}"):
        legacy = "" if value is None else str(value)
        openid = mapping.get(legacy)
        if openid and openid != legacy:
            pairs.append((legacy, openid))
    return pairs


def _mapping_for(kind: str, users: dict[str, str], groups: dict[str, str]) -> dict[str, str]:
    if kind == "group":
        return groups
    if kind == "private":
        return users
    return {}


def _fetch(conn: sqlite3.Connection, table: str, column: str, value: Any) -> sqlite3.Row | None:
    return conn.execute(f"SELECT * FROM {table} WHERE {column}=?", (value,)).fetchone()


def _delete(conn: sqlite3.Connection, table: str, **columns: Any) -> None:
    clause = " AND ".join(f"{name}=?" for name in columns)
    conn.execute(f"DELETE FROM {table} WHERE {clause}", tuple(columns.values()))


def _backup(
    conn: sqlite3.Connection,
    run_at: str,
    table: str,
    old_key: str,
    new_key: str,
    row: sqlite3.Row,
) -> None:
    """删除/合并旧行前整行留档（同事务，回滚时一起回滚）。"""
    conn.execute(
        f"INSERT INTO {_BACKUP_TABLE} (run_at, table_name, old_key, new_key, payload) VALUES (?, ?, ?, ?, ?)",
        (run_at, table, old_key, new_key, json.dumps(dict(row), ensure_ascii=False, default=str)),
    )


# shortcut: DATETIME 由 SQLAlchemy 按同一 ISO 文本格式写库，先按字符串比新旧；
# 一旦有别的格式写入，改成解析后比较。
def _newer(left: Any, right: Any) -> Any:
    if left is None:
        return right
    if right is None:
        return left
    return left if str(left) >= str(right) else right


def _later_deadline(left: Any, right: Any) -> Any:
    """两个静默截止时间取较晚的（映射合并撞 key 时不让静默提前失效）。"""
    try:
        return left if datetime.fromisoformat(str(left)) >= datetime.fromisoformat(str(right)) else right
    except ValueError:
        return max(str(left), str(right))


def _update_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    mapping: dict[str, str],
    counts: dict[str, int],
) -> None:
    """无唯一约束的列直接改写（多列各自调用，冲突由表本身决定）。"""
    for legacy, openid in _legacy_ids(conn, table, column, mapping):
        cursor = conn.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (openid, legacy))
        _bump(counts, table, cursor.rowcount)


def _run_table(conn: sqlite3.Connection, table: str, action: Callable[[], None], log: Logger) -> None:
    """一张表一个 savepoint：缺表/缺列只跳过该表，不拖累已经改好的其它表。"""
    conn.execute("SAVEPOINT migrate_table")
    try:
        action()
    except sqlite3.OperationalError as exc:
        conn.execute("ROLLBACK TO migrate_table")
        conn.execute("RELEASE migrate_table")
        log.debug("插件库缺表或缺列，跳过该表", table=table, error=str(exc))
    else:
        conn.execute("RELEASE migrate_table")


# ── streaming_parser ─────────────────────────────────────────────────────


def _migrate_subscriptions(
    conn: sqlite3.Connection,
    groups: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """(group_id, platform, room_id) 唯一：目标群已订阅同一直播间时合并旧行后删。"""
    for legacy, openid in _legacy_ids(conn, "subscriptions", "group_id", groups):
        rows = conn.execute("SELECT * FROM subscriptions WHERE group_id=?", (legacy,)).fetchall()
        for row in rows:
            target = conn.execute(
                "SELECT * FROM subscriptions WHERE group_id=? AND platform=? AND room_id=? LIMIT 1",
                (openid, row["platform"], row["room_id"]),
            ).fetchone()
            if target is None:
                conn.execute("UPDATE subscriptions SET group_id=? WHERE id=?", (openid, row["id"]))
            else:
                # 合并线上行为：推送开关 OR（用户可能只在任一 channel 关过），名称目标非空优先。
                conn.execute(
                    "UPDATE subscriptions SET push_live=?, push_live_end=?, name=? WHERE id=?",
                    (
                        int(bool(target["push_live"]) or bool(row["push_live"])),
                        int(bool(target["push_live_end"]) or bool(row["push_live_end"])),
                        target["name"] or row["name"],
                        target["id"],
                    ),
                )
                _backup(conn, run_at, "subscriptions", legacy, openid, row)
                conn.execute("DELETE FROM subscriptions WHERE id=?", (row["id"],))
            _bump(counts, "subscriptions", 1)


def _migrate_group_settings(
    conn: sqlite3.Connection,
    groups: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """group_id 主键：目标行已存在时合并（目标非空优先 / 布尔 OR / updated_at 取新）。"""
    for legacy, openid in _legacy_ids(conn, "group_settings", "group_id", groups):
        old = _fetch(conn, "group_settings", "group_id", legacy)
        if old is None:
            continue
        new = _fetch(conn, "group_settings", "group_id", openid)
        if new is None:
            conn.execute("UPDATE group_settings SET group_id=? WHERE group_id=?", (openid, legacy))
        else:
            conn.execute(
                "UPDATE group_settings SET card_style=?, ai_reply_live=?, ai_reply_live_end=?, "
                "default_push_live=?, default_push_live_end=?, updated_at=? WHERE group_id=?",
                (
                    new["card_style"] or old["card_style"],
                    int(bool(new["ai_reply_live"]) or bool(old["ai_reply_live"])),
                    int(bool(new["ai_reply_live_end"]) or bool(old["ai_reply_live_end"])),
                    int(bool(new["default_push_live"]) or bool(old["default_push_live"])),
                    int(bool(new["default_push_live_end"]) or bool(old["default_push_live_end"])),
                    _newer(new["updated_at"], old["updated_at"]),
                    openid,
                ),
            )
            _backup(conn, run_at, "group_settings", legacy, openid, old)
            _delete(conn, "group_settings", group_id=legacy)
        _bump(counts, "group_settings", 1)


def _migrate_streaming_parser(
    conn: sqlite3.Connection,
    users: dict[str, str],
    groups: dict[str, str],
    run_at: str,
    counts: dict[str, int],
    log: Logger,
    official_only: bool,
) -> None:
    if not official_only:  # 群订阅/设置是活跃绑定，dual/OneBot 下不能改（入口已整库跳过）
        return
    _run_table(conn, "subscriptions", lambda: _migrate_subscriptions(conn, groups, run_at, counts), log)
    _run_table(conn, "group_settings", lambda: _migrate_group_settings(conn, groups, run_at, counts), log)


# ── minigame ─────────────────────────────────────────────────────────────


def _migrate_mg_profiles(
    conn: sqlite3.Connection,
    users: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """user_id 主键：分数相加、最高分取大、场次/胜场相加、昵称目标非空优先。"""
    has_user_name = "user_name" in _columns(conn, "mg_profile")
    for legacy, openid in _legacy_ids(conn, "mg_profile", "user_id", users):
        old = _fetch(conn, "mg_profile", "user_id", legacy)
        if old is None:
            continue
        new = _fetch(conn, "mg_profile", "user_id", openid)
        if new is None:
            conn.execute("UPDATE mg_profile SET user_id=? WHERE user_id=?", (openid, legacy))
        else:
            merged: dict[str, Any] = {
                "score": int(new["score"] or 0) + int(old["score"] or 0),
                "best_score": max(int(new["best_score"] or 0), int(old["best_score"] or 0)),
                "plays": int(new["plays"] or 0) + int(old["plays"] or 0),
                "wins": int(new["wins"] or 0) + int(old["wins"] or 0),
                "updated_at": _newer(new["updated_at"], old["updated_at"]),
            }
            if has_user_name:  # v1/v2 老库还没这列（插件 v2 迁移才加）
                merged["user_name"] = str(new["user_name"] or old["user_name"] or "")
            assignments = ", ".join(f"{column}=?" for column in merged)
            conn.execute(
                f"UPDATE mg_profile SET {assignments} WHERE user_id=?",
                (*merged.values(), openid),
            )
            _backup(conn, run_at, "mg_profile", legacy, openid, old)
            _delete(conn, "mg_profile", user_id=legacy)
        _bump(counts, "mg_profile", 1)


def _migrate_mg_daily(
    conn: sqlite3.Connection,
    users: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """(user_id, game_id, day) 主键：冲突时场次相加。"""
    for legacy, openid in _legacy_ids(conn, "mg_daily", "user_id", users):
        rows = conn.execute("SELECT * FROM mg_daily WHERE user_id=?", (legacy,)).fetchall()
        for row in rows:
            taken = conn.execute(
                "SELECT 1 FROM mg_daily WHERE user_id=? AND game_id=? AND day=?",
                (openid, row["game_id"], row["day"]),
            ).fetchone()
            if taken is None:
                conn.execute(
                    "UPDATE mg_daily SET user_id=? WHERE user_id=? AND game_id=? AND day=?",
                    (openid, legacy, row["game_id"], row["day"]),
                )
            else:
                conn.execute(
                    "UPDATE mg_daily SET plays=plays+? WHERE user_id=? AND game_id=? AND day=?",
                    (row["plays"], openid, row["game_id"], row["day"]),
                )
                _backup(conn, run_at, "mg_daily", legacy, openid, row)
                _delete(conn, "mg_daily", user_id=legacy, game_id=row["game_id"], day=row["day"])
            _bump(counts, "mg_daily", 1)


def _migrate_mg_checkin(
    conn: sqlite3.Connection,
    users: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """(user_id, day) 主键：冲突时积分相加、连续天数取大、首次签到取早。"""
    for legacy, openid in _legacy_ids(conn, "mg_checkin", "user_id", users):
        rows = conn.execute("SELECT * FROM mg_checkin WHERE user_id=?", (legacy,)).fetchall()
        for row in rows:
            taken = conn.execute("SELECT 1 FROM mg_checkin WHERE user_id=? AND day=?", (openid, row["day"])).fetchone()
            if taken is None:
                conn.execute(
                    "UPDATE mg_checkin SET user_id=? WHERE user_id=? AND day=?",
                    (openid, legacy, row["day"]),
                )
            else:
                conn.execute(
                    "UPDATE mg_checkin SET score=score+?, streak=MAX(streak, ?), "
                    "created_at=MIN(created_at, ?) WHERE user_id=? AND day=?",
                    (row["score"], row["streak"], row["created_at"], openid, row["day"]),
                )
                _backup(conn, run_at, "mg_checkin", legacy, openid, row)
                _delete(conn, "mg_checkin", user_id=legacy, day=row["day"])
            _bump(counts, "mg_checkin", 1)


def _migrate_mg_fortune(
    conn: sqlite3.Connection,
    users: dict[str, str],
    run_at: str,
    counts: dict[str, int],
) -> None:
    """(user_id, day) 主键：冲突保留目标（已抽到的那支签），旧行留档后删。"""
    for legacy, openid in _legacy_ids(conn, "mg_fortune", "user_id", users):
        rows = conn.execute("SELECT * FROM mg_fortune WHERE user_id=?", (legacy,)).fetchall()
        for row in rows:
            taken = conn.execute("SELECT 1 FROM mg_fortune WHERE user_id=? AND day=?", (openid, row["day"])).fetchone()
            if taken is None:
                conn.execute(
                    "UPDATE mg_fortune SET user_id=? WHERE user_id=? AND day=?",
                    (openid, legacy, row["day"]),
                )
            else:
                _backup(conn, run_at, "mg_fortune", legacy, openid, row)
                _delete(conn, "mg_fortune", user_id=legacy, day=row["day"])
            _bump(counts, "mg_fortune", 1)


def _migrate_mg_bottle_columns(conn: sqlite3.Connection, users: dict[str, str], counts: dict[str, int]) -> None:
    _update_column(conn, "mg_bottle", "sender_id", users, counts)
    _update_column(conn, "mg_bottle", "picked_by", users, counts)


def _migrate_mg_bottle_meta(
    conn: sqlite3.Connection,
    users: dict[str, str],
    groups: dict[str, str],
    counts: dict[str, int],
    log: Logger,
) -> None:
    """mg_bottle.meta 内嵌会话 ID（写入见 games/bottle.py 的 meta["conversation"]）。"""
    rows = conn.execute("SELECT id, meta FROM mg_bottle WHERE meta IS NOT NULL").fetchall()
    for row in rows:
        try:
            data = json.loads(row["meta"])
        except (TypeError, ValueError):
            log.debug("瓶子 meta 不是合法 JSON，保持原样", bottle_id=row["id"])
            continue
        if not isinstance(data, dict):
            continue
        changed = False
        for key in ("conversation", "conversation_id"):
            legacy = str(data.get(key) or "")
            openid = groups.get(legacy) or users.get(legacy)
            if not openid or openid == legacy:
                continue
            data[key] = openid
            changed = True
        if not changed:
            continue
        conn.execute(
            "UPDATE mg_bottle SET meta=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), row["id"]),
        )
        _bump(counts, "mg_bottle", 1)


def _migrate_mg_record_conversations(
    conn: sqlite3.Connection,
    users: dict[str, str],
    groups: dict[str, str],
    counts: dict[str, int],
) -> None:
    """mg_record 没有会话类型列：会话 ID 先按群、再按用户映射（同插件 v4 迁移）。"""
    pairs: list[tuple[str, str]] = []
    for (value,) in conn.execute("SELECT DISTINCT conversation_id FROM mg_record"):
        legacy = "" if value is None else str(value)
        openid = groups.get(legacy) or users.get(legacy)
        if openid and openid != legacy:
            pairs.append((legacy, openid))
    for legacy, openid in pairs:
        cursor = conn.execute("UPDATE mg_record SET conversation_id=? WHERE conversation_id=?", (openid, legacy))
        _bump(counts, "mg_record", cursor.rowcount)


def _migrate_minigame(
    conn: sqlite3.Connection,
    users: dict[str, str],
    groups: dict[str, str],
    run_at: str,
    counts: dict[str, int],
    log: Logger,
    official_only: bool,
) -> None:
    _run_table(conn, "mg_profile", lambda: _migrate_mg_profiles(conn, users, run_at, counts), log)
    _run_table(conn, "mg_daily", lambda: _migrate_mg_daily(conn, users, run_at, counts), log)
    _run_table(conn, "mg_checkin", lambda: _migrate_mg_checkin(conn, users, run_at, counts), log)
    _run_table(conn, "mg_fortune", lambda: _migrate_mg_fortune(conn, users, run_at, counts), log)
    _run_table(conn, "mg_bottle", lambda: _migrate_mg_bottle_columns(conn, users, counts), log)
    if official_only:
        # 会话类绑定：dual/OneBot 模式下 OneBot 仍按真实数字 ID 使用，不迁。
        _run_table(conn, "mg_bottle", lambda: _migrate_mg_bottle_meta(conn, users, groups, counts, log), log)
    _run_table(conn, "mg_record", lambda: _update_column(conn, "mg_record", "user_id", users, counts), log)
    if official_only:
        _run_table(
            conn,
            "mg_record",
            lambda: _migrate_mg_record_conversations(conn, users, groups, counts),
            log,
        )


# ── starship ─────────────────────────────────────────────────────────────


def _migrate_starship(
    conn: sqlite3.Connection,
    users: dict[str, str],
    groups: dict[str, str],
    run_at: str,
    counts: dict[str, int],
    log: Logger,
    official_only: bool,
) -> None:
    # 榜单没有唯一约束，同一个人多行是正常历史成绩，直接改列即可。
    _run_table(
        conn,
        "starship_scores",
        lambda: _update_column(conn, "starship_scores", "user_id", users, counts),
        log,
    )


_MIGRATORS: dict[str, _Migrator] = {
    "streaming_parser": _migrate_streaming_parser,
    "minigame": _migrate_minigame,
    "starship": _migrate_starship,
}


def _migrate_database(
    path: Path,
    plugin_name: str,
    users: dict[str, str],
    groups: dict[str, str],
    log: Logger,
    *,
    official_only: bool,
) -> dict[str, int]:
    """一个库一个事务、表级 savepoint；连接级异常回滚整库并只记 WARNING。"""
    run_at = datetime.now(UTC).isoformat(timespec="seconds")
    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(path, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(_BACKUP_DDL)
                _MIGRATORS[plugin_name](conn, users, groups, run_at, counts, log, official_only)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - 迁移不是启动硬依赖，失败降级为告警
        log.warning(
            "插件独立库身份迁移失败，旧数据保持原样",
            plugin=plugin_name,
            database=str(path),
            error=str(exc),
        )
        return {}
    return counts


# ── speaking_schedule：config.toml / mutes.json ──────────────────────────


def _backup_file(path: Path) -> Path:
    """写前把原文件留档到同目录：<name>.identity-backup-<时间戳>。"""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    backup = path.with_name(f"{path.name}.identity-backup-{stamp}")
    shutil.copy2(path, backup)
    return backup


def _atomic_write(path: Path, text: str) -> None:
    """同目录临时文件 + fsync + os.replace：崩溃时不会留下半个配置文件。"""
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _migrate_speaking_config(
    path: Path,
    users: dict[str, str],
    groups: dict[str, str],
    log: Logger,
) -> int:
    """overrides[].id 按 kind 改写；两条旧 id 映射到同一会话时留第一条（插件校验不允许重复）。"""
    doc = tomlkit.parse(path.read_text(encoding="utf-8-sig"))
    overrides = doc.get("overrides") or []
    kept: list[Any] = []
    seen: set[tuple[str, str]] = set()
    changed = dropped = 0
    for override in overrides:
        if not hasattr(override, "get"):
            continue
        kind = str(override.get("kind") or "")
        legacy = str(override.get("id") or "").strip()
        openid = _mapping_for(kind, users, groups).get(legacy)
        if openid and openid != legacy:
            override["id"] = openid
            changed += 1
        token = (kind, str(override.get("id") or ""))
        if token in seen:
            dropped += 1
            continue
        seen.add(token)
        kept.append(override)
    if not changed and not dropped:
        return 0
    _backup_file(path)
    if dropped:
        table = tomlkit.aot()
        for item in kept:
            table.append(item)
        doc["overrides"] = table
        log.warning("作息覆盖项合并后重复，已留第一条", file=str(path), dropped=dropped)
    _atomic_write(path, tomlkit.dumps(doc))
    return changed


def _migrate_speaking_mutes(
    path: Path,
    users: dict[str, str],
    groups: dict[str, str],
    log: Logger,
) -> int:
    """mutes.json 的 group:<id>/private:<id> scope 改写；同账号撞 key 取较晚截止时间。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("mutes.json 顶层不是对象")
    changed = 0
    for scopes in data.values():
        if not isinstance(scopes, dict):
            continue
        for scope in list(scopes):
            kind, separator, local = str(scope).partition(":")
            if not separator:
                continue
            openid = _mapping_for(kind, users, groups).get(local)
            if not openid or openid == local:
                continue
            deadline = scopes.pop(scope)
            new_scope = f"{kind}:{openid}"
            if new_scope in scopes:
                deadline = _later_deadline(deadline, scopes[new_scope])
            scopes[new_scope] = deadline
            changed += 1
    if not changed:
        return 0
    _backup_file(path)
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    return changed


def _migrate_speaking_files(
    root: Path,
    users: dict[str, str],
    groups: dict[str, str],
    log: Logger,
) -> dict[str, int]:
    directory = root / _SPEAKING_SCHEDULE
    counts: dict[str, int] = {}
    for filename, migrate in (
        (_SPEAKING_CONFIG, _migrate_speaking_config),
        (_SPEAKING_MUTES, _migrate_speaking_mutes),
    ):
        path = directory / filename
        if not path.is_file():
            continue
        try:
            changed = migrate(path, users, groups, log)
        except Exception as exc:  # noqa: BLE001 - 坏 TOML/JSON 只告警，文件保持原样
            log.warning(
                "插件配置文件身份迁移失败，文件保持原样",
                plugin=_SPEAKING_SCHEDULE,
                file=str(path),
                error=str(exc),
            )
            continue
        if changed:
            counts[filename] = changed
    return counts


def migrate_plugin_databases(
    plugins_data_dir: str | Path,
    *,
    user_map: dict[str, str],
    group_map: dict[str, str],
    official_only: bool = False,
    logger: Logger | None = None,
) -> dict[str, dict[str, int]]:
    """把插件独立库/配置里的旧数字 ID 改写成 official openid；返回各来源改写行数。

    user_map = 旧 QQ 号 → openid，group_map = 旧群号 → openid，由调用方构造。
    official_only=False（dual/OneBot 模式）时跳过群/会话绑定：streaming_parser 库
    与 speaking_schedule 文件整体跳过，minigame 只迁用户级列。库/文件不存在或无
    需要迁移的行时 no-op；单库/单文件失败只 WARNING 不抛，重复调用幂等。
    """
    if not user_map and not group_map:
        return {}
    log = logger or NullLogger()
    root = Path(plugins_data_dir)
    result: dict[str, dict[str, int]] = {}
    for plugin_name, relative in _DATABASES:
        if plugin_name == "streaming_parser" and not official_only:
            continue  # 订阅/群设置是活跃群绑定，mixed 模式下 OneBot 仍在用真实群号
        path = root / relative
        if not path.is_file():
            continue
        counts = _migrate_database(path, plugin_name, user_map, group_map, log, official_only=official_only)
        if not counts:
            continue
        result[plugin_name] = counts
        log.info(
            "插件独立库身份迁移完成",
            plugin=plugin_name,
            migrated=sum(counts.values()),
            tables=counts,
        )
    if official_only:
        file_counts = _migrate_speaking_files(root, user_map, group_map, log)
        if file_counts:
            result[_SPEAKING_SCHEDULE] = file_counts
            log.info(
                "插件配置身份迁移完成",
                plugin=_SPEAKING_SCHEDULE,
                migrated=sum(file_counts.values()),
                files=file_counts,
            )
    return result
