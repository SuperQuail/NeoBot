"""面板档案管理：查看 / 编辑 / 删除档案记忆（features/spec(2)）。

设计要点（照 spec §4 执行）：
- **不新建数据层**：全部转调既有的 ArchiveMemoryService（模型侧 CRUD 用的同一套）；
- 列表**不返回完整 value**（只返回预览 + 字符数），只有单条详情才给全文，避免大档案塞爆浏览器；
- 编辑走**乐观锁**（version），冲突返回 409 并带当前内容，由前端提示「已被他人修改」；
- 删除是**硬删除**（本期不做回收站），但要求独立开关 + 二次确认 + 审计日志（调用方负责日志）；
- 内部表（memory_counter 等）在 UI 上要有明确警告，且**禁止编辑**（改坏会导致重复/漏总结）。
"""

from __future__ import annotations

from typing import Any, Iterable

#: 列表条目返回的内容预览字符数（详情接口才返回全文）。
PREVIEW_CHARS = 200
#: 列表分页上限（防止一次拉爆）。
MAX_LIST_LIMIT = 200

#: 内部表：面板只读/只删、不可编辑，且 UI 必须给出警告。
#: 目前唯一的内部表是 memory_counter（待总结消息 JSON），删它会重置自动总结计数。
INTERNAL_TABLES: frozenset[str] = frozenset({"memory_counter"})

_INTERNAL_TABLE_NOTES: dict[str, str] = {
    "memory_counter": "自动总结的内部计数表（待总结消息）。删除会把该会话的自动总结计数清零，"
    "导致下一轮重新开始累积；内容由程序维护，禁止手工编辑。",
}

#: 前缀警告：这些表存的是长期记忆，误删不可恢复。
_TABLE_NOTES: dict[str, str] = {
    "user_profile": "用户长期档案。删除后模型将忘记该用户的历史设定。",
    "group_profile": "群聊长期档案。删除后模型将忘记该群的历史设定。",
    "user_summary": "用户档案的历史小结。",
    "group_summary": "群聊档案的历史小结。",
    "item_archive": "物品档案。",
}


def table_note(table_name: str) -> str:
    """给某张表附上一句人话警告（内部表优先）。"""
    name = str(table_name or "").strip()
    if name in INTERNAL_TABLES:
        return _INTERNAL_TABLE_NOTES.get(name, "这是程序维护的内部表。")
    return _TABLE_NOTES.get(name, "")


def is_internal_table(table_name: str) -> bool:
    return str(table_name or "").strip() in INTERNAL_TABLES


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _preview(value: str, limit: int = PREVIEW_CHARS) -> tuple[str, bool]:
    text = _text(value)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _timestamp(value: Any) -> str:
    """把 datetime / 任意时间值序列化为 ISO8601 字符串（缺失返回空串）。"""
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())
        except Exception:
            return ""
    return str(value)


def item_summary(item: Any, *, preview_chars: int = PREVIEW_CHARS) -> dict[str, Any]:
    """列表用条目摘要：**不含完整 value**。"""
    value = _text(getattr(item, "value", ""))
    preview, truncated = _preview(value, preview_chars)
    tags = getattr(item, "tags", None) or []
    return {
        "table_name": _text(getattr(item, "table_name", "")),
        "key": _text(getattr(item, "key", "")),
        "preview": preview,
        "preview_truncated": truncated,
        "total_chars": len(value),
        "tags": [_text(tag) for tag in tags],
        "version": int(getattr(item, "version", 0) or 0),
        "created_at": _timestamp(getattr(item, "created_at", None)),
        "updated_at": _timestamp(getattr(item, "updated_at", None)),
        "internal": is_internal_table(getattr(item, "table_name", "")),
    }


def item_detail(item: Any) -> dict[str, Any]:
    """单条详情：返回全文（不截断）。"""
    payload = item_summary(item, preview_chars=0)
    payload["value"] = _text(getattr(item, "value", ""))
    payload["preview"] = payload["value"]
    payload["preview_truncated"] = False
    payload["editable"] = not is_internal_table(getattr(item, "table_name", ""))
    payload["note"] = table_note(getattr(item, "table_name", ""))
    return payload


def _over_limit_map(rows: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            name = _text(row.get("table_name"))
        else:
            name = _text(getattr(row, "table_name", ""))
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


async def list_tables(service: Any) -> dict[str, Any]:
    """档案表清单 + 每表条目数 / 最大长度 / 超限条目数（spec §4.1 方案 A）。

    引擎等来源异常一律吞掉并回落为「无数据」，不能让面板 500。
    """
    limit = _service_max_total_chars(service)
    try:
        names = [str(name) for name in (await service.list_table_names() or [])]
    except Exception:
        names = []
    try:
        stats = {str(row.get("table_name")): row for row in (await service.table_stats() or [])}
    except Exception:
        stats = {}
    over_limit: dict[str, int] = {}
    if limit > 0:
        try:
            over_limit = _over_limit_map(await service.list_over_limit(limit=MAX_LIST_LIMIT) or [])
        except Exception:
            over_limit = {}

    # 超限清单里出现的表即使 stats 里没有（理论上不会）也要列出来
    for name in over_limit:
        if name not in names:
            names.append(name)

    items: list[dict[str, Any]] = []
    for name in sorted(names):
        row = stats.get(name) or {}
        count = int(row.get("count", 0) or 0)
        max_chars = int(row.get("max_value_chars", 0) or 0)
        internal = is_internal_table(name)
        items.append(
            {
                "table_name": name,
                "count": count,
                "max_value_chars": max_chars,
                "over_limit_count": int(over_limit.get(name, 0) or 0),
                "internal": internal,
                "note": table_note(name),
            }
        )
    return {
        "items": items,
        "max_total_chars": limit,
        "delete_enabled": False,  # 由 API 层按配置覆盖
        "readonly_reason": "",
    }


def _service_max_total_chars(service: Any) -> int:
    try:
        return int(getattr(service, "max_total_chars", 0) or 0)
    except Exception:
        return 0


async def list_items(
    service: Any,
    *,
    table: str,
    key_query: str = "",
    value_query: str = "",
    tags: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
    over_limit_only: bool = False,
) -> dict[str, Any]:
    """按表分页列出档案条目（转调服务层 list，服务端筛选）。"""
    safe_limit = max(1, min(int(limit or 50), MAX_LIST_LIMIT))
    safe_offset = max(0, int(offset or 0))
    items = await service.list(
        table,
        tags=list(tags or []) or None,
        key_query=key_query or None,
        value_query=value_query or None,
        limit=safe_limit,
        offset=safe_offset,
    )
    summaries = [item_summary(item) for item in (items or [])]
    if over_limit_only:
        summaries = [row for row in summaries if row["total_chars"] > _service_max_total_chars(service)]
    return {
        "items": summaries,
        "table": table,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": len(summaries) >= safe_limit,
    }


async def list_over_limit(service: Any, *, table: str = "", limit: int = 100) -> dict[str, Any]:
    """当前超过存储上限的档案（spec(1) A7 的可视化落点）。"""
    rows = await service.list_over_limit(
        table_name=table or None, limit=max(1, min(int(limit or 100), MAX_LIST_LIMIT))
    )
    return {"items": [dict(row) for row in (rows or [])], "max_total_chars": _service_max_total_chars(service)}


async def get_item(service: Any, *, table: str, key: str) -> dict[str, Any] | None:
    item = await service.get(table, key)
    if item is None:
        return None
    return item_detail(item)


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


__all__ = [
    "INTERNAL_TABLES",
    "MAX_LIST_LIMIT",
    "PREVIEW_CHARS",
    "get_item",
    "is_internal_table",
    "item_detail",
    "item_summary",
    "list_items",
    "list_over_limit",
    "list_tables",
    "normalize_tags",
    "table_note",
]
