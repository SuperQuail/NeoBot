"""agent 工具状态库（state/events/receipts）的旧 ID 迁移。

核心库迁移（identity_data_migration）的附属部分：启动期与 /linkqq、/linkgroup
之后由 migrate_identity_data 调用，不单独对外。每个库单事务：

- state 的 owner/chat 中 group:<旧ID> / private:<旧ID> 改写成 openid；目标行已
  存在时合并 document（todos/questions 并集去重；plan/goal 目标状态机字段优先、
  文本按「旧 + 空行 + 新」拼接；目标 JSON 损坏时按空文档合并源文档，至少保留
  源），源行与被覆盖的目标行都先写 identity_migration_backup 再删旧行；
- events 改 owner/chat；receipts 冲突时保留目标、旧行备份后删除。

失败只记 WARNING 不阻断启动；重复执行幂等。共用工具函数从核心迁移模块导入，
避免两处各写一份。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger

from .identity_data_migration import (
    _backup,
    _bump,
    _connect,
    _ensure_backup,
    _fetch_where,
    _json_dump,
    _table_exists,
)


def _map_scoped_id(mappings: Any, value: Any) -> str:
    """owner/chat 形如 group:<id> / private:<id>[:main]，只改中间那段 ID。"""
    text = str(value or "")
    for kind in ("group", "private"):
        prefix = f"{kind}:"
        if not text.startswith(prefix):
            continue
        local, separator, suffix = text[len(prefix):].partition(":")
        new_id = mappings.for_kind(kind).get(local)
        return f"{prefix}{new_id}{separator}{suffix}" if new_id and new_id != local else text
    return text


def _merge_agent_items(source_items: Any, target_items: Any, *, key: str | None) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*(target_items or []), *(source_items or [])]:
        token = (
            str(item.get(key))
            if key and isinstance(item, dict) and item.get(key)
            else _json_dump(item, sort_keys=True)
        )
        if token not in seen:
            seen.add(token)
            merged.append(item)
    return merged


def _merge_agent_named(source: Any, target: Any, *, text_key: str) -> Any:
    """plan/goal：保留目标对象的状态机字段，文本字段按「旧 + 空行 + 新」拼接。"""
    if not target:
        return source
    if not source:
        return target
    if isinstance(source, dict) and isinstance(target, dict):
        merged = dict(target)
        old_text, new_text = source.get(text_key), target.get(text_key)
        if isinstance(old_text, str) and isinstance(new_text, str) and old_text and new_text:
            merged[text_key] = f"{old_text}\n\n{new_text}"
        elif text_key not in target and old_text is not None:
            merged[text_key] = old_text
        return merged
    if isinstance(source, str) and isinstance(target, str):
        return f"{source}\n\n{target}" if source and target else source or target
    return target


def _merge_agent_document(source_raw: Any, target_raw: Any) -> str:
    """目标文档优先；目标 JSON 损坏时按空文档合并源文档（至少保留源）。"""
    try:
        target = json.loads(target_raw)
    except (TypeError, ValueError):
        target = {}
    if not isinstance(target, dict):
        target = {}
    try:
        source = json.loads(source_raw)
    except (TypeError, ValueError):
        source = {}
    if not isinstance(source, dict):
        source = {}
    merged = dict(target)
    for name, value in source.items():
        merged.setdefault(name, value)
    merged["todos"] = _merge_agent_items(source.get("todos"), target.get("todos"), key="content")
    merged["questions"] = _merge_agent_items(
        source.get("questions"), target.get("questions"), key="question_id"
    )
    merged["plan"] = _merge_agent_named(source.get("plan"), target.get("plan"), text_key="plan")
    merged["goal"] = _merge_agent_named(
        source.get("goal"), target.get("goal"), text_key="objective"
    )
    return _json_dump(merged)


def _migrate_agent_state_rows(
    conn: sqlite3.Connection, mappings: Any, run_at: str, counts: dict[str, int]
) -> None:
    rows = conn.execute("SELECT owner, chat, agent, document FROM state").fetchall()
    for row in rows:
        new_owner = _map_scoped_id(mappings, row["owner"])
        new_chat = _map_scoped_id(mappings, row["chat"])
        if new_owner == row["owner"] and new_chat == row["chat"]:
            continue
        target = _fetch_where(conn, "state", owner=new_owner, chat=new_chat, agent=row["agent"])
        if target is None:
            conn.execute(
                "UPDATE state SET owner=?, chat=? WHERE owner=? AND chat=? AND agent=?",
                (new_owner, new_chat, row["owner"], row["chat"], row["agent"]),
            )
        else:
            old_key = f"{row['owner']}|{row['chat']}|{row['agent']}"
            new_key = f"{new_owner}|{new_chat}|{row['agent']}"
            _backup(
                conn, run_at, "state", old_key, new_key,
                _json_dump({
                    "owner": row["owner"], "chat": row["chat"],
                    "agent": row["agent"], "document": row["document"],
                }),
            )
            # 目标行文档会被合并覆盖，先留档；目标 JSON 损坏时也能原样找回。
            _backup(
                conn, run_at, "state", new_key, new_key,
                _json_dump({
                    "owner": target["owner"], "chat": target["chat"],
                    "agent": target["agent"], "document": target["document"],
                }),
            )
            conn.execute(
                "UPDATE state SET document=? WHERE owner=? AND chat=? AND agent=?",
                (
                    _merge_agent_document(row["document"], target["document"]),
                    new_owner, new_chat, row["agent"],
                ),
            )
            conn.execute(
                "DELETE FROM state WHERE owner=? AND chat=? AND agent=?",
                (row["owner"], row["chat"], row["agent"]),
            )
        _bump(counts, "agent_state", 1)


def _migrate_agent_events(
    conn: sqlite3.Connection, mappings: Any, counts: dict[str, int]
) -> None:
    rows = conn.execute("SELECT id, owner, chat FROM events").fetchall()
    for row in rows:
        new_owner = _map_scoped_id(mappings, row["owner"])
        new_chat = _map_scoped_id(mappings, row["chat"])
        if new_owner == row["owner"] and new_chat == row["chat"]:
            continue
        conn.execute(
            "UPDATE events SET owner=?, chat=? WHERE id=?", (new_owner, new_chat, row["id"])
        )
        _bump(counts, "agent_events", 1)


def _migrate_agent_receipts(
    conn: sqlite3.Connection, mappings: Any, run_at: str, counts: dict[str, int]
) -> None:
    rows = conn.execute("SELECT owner, chat, message_id FROM receipts").fetchall()
    for row in rows:
        new_owner = _map_scoped_id(mappings, row["owner"])
        new_chat = _map_scoped_id(mappings, row["chat"])
        if new_owner == row["owner"] and new_chat == row["chat"]:
            continue
        target = _fetch_where(
            conn, "receipts", owner=new_owner, chat=new_chat, message_id=row["message_id"]
        )
        if target is None:
            conn.execute(
                "UPDATE receipts SET owner=?, chat=? WHERE owner=? AND chat=? AND message_id=?",
                (new_owner, new_chat, row["owner"], row["chat"], row["message_id"]),
            )
        else:
            old_key = f"{row['owner']}|{row['chat']}|{row['message_id']}"
            new_key = f"{new_owner}|{new_chat}|{row['message_id']}"
            _backup(
                conn, run_at, "receipts", old_key, new_key,
                _json_dump({
                    "owner": row["owner"], "chat": row["chat"],
                    "message_id": row["message_id"],
                }),
            )
            conn.execute(
                "DELETE FROM receipts WHERE owner=? AND chat=? AND message_id=?",
                (row["owner"], row["chat"], row["message_id"]),
            )
        _bump(counts, "agent_receipts", 1)


def migrate_agent_state_db(
    db_path: Path, mappings: Any, *, run_at: str, log: Logger
) -> dict[str, int]:
    """迁移 agent 状态库；库不存在直接 no-op，任何异常只 WARNING 并回滚整库。"""
    counts: dict[str, int] = {}
    if not db_path.is_file():
        return counts
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        with conn:
            _ensure_backup(conn)
            if _table_exists(conn, "state"):
                _migrate_agent_state_rows(conn, mappings, run_at, counts)
            if _table_exists(conn, "events"):
                _migrate_agent_events(conn, mappings, counts)
            if _table_exists(conn, "receipts"):
                _migrate_agent_receipts(conn, mappings, run_at, counts)
    except Exception as exc:  # 迁移是 best-effort：任何解析/DB 异常都不能阻断启动
        log.warning("身份数据迁移失败，agent 状态库保持原样", path=str(db_path), error=str(exc))
        return {}
    finally:
        if conn is not None:
            conn.close()
    return counts
