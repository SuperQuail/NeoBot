"""共享的日志快照：先脱敏，再交给各出口；不携带活的异常或业务对象。"""

from __future__ import annotations

import json
import math
import re
import traceback
from datetime import datetime
from itertools import islice
from typing import Any

from .log_exceptions import safe_rich_trace

REDACTED = "***REDACTED***"
_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)(?<![A-Za-z0-9])[A-Za-z0-9_]*"
        r"(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|password|"
        r"passwd|pwd|secret|credential|authorization)"
        r"\s*[=:]\s*(?:(?:bearer|token)\s+)?[^\s,;\"']+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:password|passwd|pwd|secret|token|api[_-]?key)"
        r"(?:\s+is)?\s*[=:]?\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{6,}"
    ),
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"),
)
_SECRET_FIELD = re.compile(
    r"(?i)(?:api[_-]?key|apikey|token|password|passwd|pwd|secret|"
    r"credential|authorization|cookie|set-cookie)$"
)
_NORMALIZED = object()


def redact_sensitive(text: str) -> str:
    for pattern in _PATTERNS:
        replacement = rf"\1{REDACTED}@" if pattern is _PATTERNS[-1] else REDACTED
        text = pattern.sub(replacement, text)
    return text


def _text(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return f"<{type(value).__name__}>"


def safe_fields(value: Any, *, depth: int = 0) -> Any:
    """复制为有界、JSON 可序列化的值；支持嵌套密钥和循环容器。"""
    if depth > 6:
        return "<max depth>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in islice(value.items(), 100):
            key = redact_sensitive(_text(key))[:200]
            result[key] = REDACTED if _SECRET_FIELD.search(key) else safe_fields(item, depth=depth + 1)
        if len(value) > 100:
            result["<truncated>"] = len(value) - 100
        return result
    if isinstance(value, (list, tuple)):
        items = [safe_fields(item, depth=depth + 1) for item in value[:100]]
        if len(value) > 100:
            items.append(f"<{len(value) - 100} more items>")
        return items
    text = redact_sensitive(_text(value))
    return text if len(text) <= 4000 else text[:4000] + "…<truncated>"


def _safe_exception(exc: Any) -> dict[str, str] | None:
    if not exc:
        return None
    exc_type, exc_value, exc_tb = exc
    if not exc_type:
        return None
    summary = traceback.TracebackException(exc_type, exc_value, exc_tb, lookup_lines=False, capture_locals=False)

    def strip_source(item: traceback.TracebackException) -> None:
        # 不读取源码和 locals：异常字符串以外的源码常量也可能是凭据。
        item.stack = traceback.StackSummary.from_list(
            [(frame.filename, frame.lineno, frame.name, "") for frame in item.stack]
        )
        # SyntaxError 另存一份源码，不在 stack 中；编译插件时同样不能输出。
        if hasattr(item, "text"):
            item.text = None
        for child in (item.__cause__, item.__context__, *(item.exceptions or ())):
            if child is not None:
                strip_source(child)

    strip_source(summary)
    return {
        "type": redact_sensitive(exc_type.__name__),
        "message": redact_sensitive(_text(exc_value)),
        "traceback": redact_sensitive("".join(summary.format())).rstrip(),
    }


def normalize_record(record: dict[str, Any]) -> bool:
    """每条 Loguru record 只处理一次，所有 sink 都使用同一份安全快照。"""
    extra = record.setdefault("extra", {})
    if extra.get("_neobot_normalized") is _NORMALIZED:
        return True
    fields = safe_fields(
        {key: value for key, value in extra.items() if not key.startswith("_") and key != "module_name"}
    )
    source = extra.get("_neobot_source", {})
    exception = _safe_exception(record.get("exception"))
    rich_trace = safe_rich_trace(record.get("exception"), redact_sensitive)
    module = redact_sensitive(_text(extra.get("module_name") or record.get("name") or "root"))
    extra.clear()
    extra.update(
        module_name=module,
        _neobot_normalized=_NORMALIZED,
        _neobot_fields=fields,
        _neobot_exception=exception,
        _neobot_rich_trace=rich_trace,
        _neobot_source=safe_fields(source),
    )
    record["message"] = redact_sensitive(record["message"])
    # 不让下游 formatter/Rich 再次渲染原始 traceback；异常数据已独立保留。
    record["exception"] = None
    return True


def record_payload(record: Any) -> dict[str, Any]:
    extra = record["extra"]
    source = extra.get("_neobot_source") or {}
    when = record["time"]
    if isinstance(when, datetime):
        timestamp = when.timestamp()
    else:
        try:
            timestamp = datetime.fromisoformat(str(when)).timestamp()
        except ValueError:
            timestamp = 0.0
    return {
        "message": redact_sensitive(record["message"]),
        "level": record["level"].name,
        "time": str(when),
        "timestamp": timestamp,
        "module": str(extra.get("module_name", "root")),
        "file": source.get("file", record["file"].name),
        "line": source.get("line", record["line"]),
        "function": source.get("function", record["function"]),
        "fields": safe_fields(extra.get("_neobot_fields", {})),
        "exception": dict(extra["_neobot_exception"]) if extra.get("_neobot_exception") else None,
    }


def fields_text(fields: dict[str, Any]) -> str:
    return " ".join(
        f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}" for key, value in fields.items()
    )


def plain_record(payload: dict[str, Any]) -> str:
    text = f"{payload['time']} | {payload['level']:<8} | {payload['module']} | {payload['message']}"
    if payload["fields"]:
        text += " | " + fields_text(payload["fields"])
    if payload["exception"]:
        text += "\n" + payload["exception"]["traceback"]
    return text
