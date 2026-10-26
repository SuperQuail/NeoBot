"""与实例状态无关的小工具函数。"""

from __future__ import annotations

import random
from typing import Any
from uuid import uuid4

from neobot_app.bilibili._compat import get_field
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.bilibili.live_parts.constants import _RECURRENCES


def _client_user_agent(client: Any) -> str:
    """取 client 实际发 HTTP 的 UA，保证 getDanmuInfo 与 WS token 绑定一致。"""
    ua = str(get_field(client, "user_agent", "") or "")
    if not ua:
        session = get_field(client, "_session", None)
        headers = getattr(session, "headers", None)
        if headers is not None:
            ua = str(headers.get("User-Agent") or "")
    return ua or DEFAULT_USER_AGENT


def _normalize_clock(value: Any) -> str | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour:02d}:{minute:02d}"


def _normalize_schedule(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    clock = _normalize_clock(value.get("time"))
    recurrence = str(value.get("recurrence") or "").strip().lower()
    prompt = str(value.get("prompt") or "").strip()
    if clock is None or recurrence not in _RECURRENCES or not prompt:
        return None
    record = {
        "id": str(value.get("id") or uuid4().hex[:12]),
        "time": clock,
        "recurrence": recurrence,
        "prompt": prompt,
        "last_fired_date": str(value.get("last_fired_date") or ""),
    }
    weekday = value.get("weekday")
    if isinstance(weekday, int) and 0 <= weekday <= 6:
        record["weekday"] = weekday
    return record


def _with_jitter(seconds: float) -> float:
    """重连退避上下浮动 20%：多房间同时掉线时不要同一秒撞回服务器。"""
    return max(0.0, float(seconds)) * random.uniform(0.8, 1.2)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
