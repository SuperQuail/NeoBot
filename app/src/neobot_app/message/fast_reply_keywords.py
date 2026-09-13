"""命中「玩法/插件关键词」时跳过 @ 提及等待的关键词表。

群聊里被 @ 之后，本体默认先等待 chat.at_mention_reply_delay_seconds（默认 5 秒）
收集上下文，再触发回复事件；这对闲聊有用，但对「签到」「抽签」这类**意图已经足够
明确**的玩法关键词只显得迟钝。于是插件在 load 时把自己的关键词登记到这里：被 @ 的
正文命中即跳过等待、直接触发回复事件。

设计边界（刻意保持很小）：

- **插件驱动**：本体不认识任何具体玩法，只问「这句话是否已经足够明确」；
- **最长关键词优先 + 大小写不敏感**：与插件侧关键词入口（minigame 的 KEYWORDS）同一套语义；
- **零 IO**：纯内存表，读路径是几次 in 比较，不阻塞消息管线；
- 注册方用 owner（通常就是插件名）标识，停用 / 卸载时按 owner 注销，不留残影；
- 读路径**绝不抛异常**：关键词表坏掉也不能影响消息管线。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: owner -> 关键词（按注册顺序，便于排查）
_registry: dict[str, tuple[str, ...]] = {}

#: 折叠后的关键词 -> (owner, 原始关键词)
_index: dict[str, tuple[str, str]] = {}


def register_reply_trigger_keywords(
    owner: str, keywords: Iterable[Any] | str | None
) -> tuple[str, ...]:
    """登记一组「命中即跳过 @ 提及等待」的关键词（同一 owner 覆盖式更新）。

    空串会被忽略；重复关键词只留一份。返回实际登记的关键词（按登记顺序）。
    """
    name = str(owner or "").strip()
    if not name:
        raise ValueError("owner 不能为空")
    values: list[Any]
    if isinstance(keywords, str):
        values = [keywords]
    else:
        values = list(keywords or ())
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    unregister_reply_trigger_keywords(name)
    if not cleaned:
        return ()
    _registry[name] = tuple(cleaned)
    for text in cleaned:
        _index.setdefault(text.casefold(), (name, text))
    return _registry[name]


def unregister_reply_trigger_keywords(owner: str) -> tuple[str, ...]:
    """注销某个 owner 登记的关键词，返回被移除的关键词（未登记则返回空）。"""
    name = str(owner or "").strip()
    removed = _registry.pop(name, ())
    for text in removed:
        key = text.casefold()
        entry = _index.get(key)
        if entry is not None and entry[0] == name:
            _index.pop(key, None)
    return removed


def match_reply_trigger_keyword(text: str) -> str:
    """正文里命中的关键词（最长优先）；没有命中返回空串。"""
    value = str(text or "")
    if not value or not _index:
        return ""
    folded = value.casefold()
    best = ""
    for keyword in _index:
        if keyword in folded and len(keyword) > len(best):
            best = keyword
    if not best:
        return ""
    return _index[best][1]


def reply_trigger_keywords() -> dict[str, tuple[str, ...]]:
    """当前登记情况（owner -> 关键词），只读快照，供测试与排查使用。"""
    return dict(_registry)


def registered_reply_trigger_owners() -> tuple[str, ...]:
    return tuple(_registry)


def reset_reply_trigger_keywords() -> None:
    """清空整张表（测试收尾 / 全量卸载用）。"""
    _registry.clear()
    _index.clear()


# ── 消息取文本（与 commands/service.py 的取法一致：只取 text 段）────────


def _segment_type(segment: Any) -> str:
    value = getattr(segment, "type", None)
    if hasattr(value, "value"):
        value = value.value
    if value is None and isinstance(segment, dict):
        value = segment.get("type")
        if hasattr(value, "value"):
            value = value.value
    return str(value or "")


def _segment_data(segment: Any) -> dict[str, Any]:
    data = getattr(segment, "data", None)
    if data is None and isinstance(segment, dict):
        data = segment.get("data")
    if isinstance(data, dict):
        return data
    dump = getattr(data, "model_dump", None)
    if callable(dump):
        try:
            value = dump(exclude_none=True)
        except Exception:  # pragma: no cover - 极端自定义段
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def message_text(message: Any) -> str:
    """尽力取消息的纯文本（text 段优先，其次 raw_message）。"""
    parts: list[str] = []
    segments = getattr(message, "message", None)
    if isinstance(segments, (list, tuple)):
        for segment in segments:
            if _segment_type(segment) != "text":
                continue
            text = _segment_data(segment).get("text")
            if text:
                parts.append(str(text))
    if parts:
        return "".join(parts)
    return str(getattr(message, "raw_message", "") or "")


def matches_reply_trigger(message: Any) -> str:
    """消息（或纯文本）是否命中「立即回复」关键词；返回命中的关键词。"""
    if isinstance(message, str):
        return match_reply_trigger_keyword(message)
    return match_reply_trigger_keyword(message_text(message))


__all__ = [
    "match_reply_trigger_keyword",
    "matches_reply_trigger",
    "message_text",
    "register_reply_trigger_keywords",
    "registered_reply_trigger_owners",
    "reply_trigger_keywords",
    "reset_reply_trigger_keywords",
    "unregister_reply_trigger_keywords",
]
