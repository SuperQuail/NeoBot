"""工具输出的截断/脱敏/参数解析等纯文本工具（无状态）。"""
from __future__ import annotations

import json
import re
from typing import Any
from neobot_app.prompt.render import render_template

#: 同一个工具 + 同一组参数连续失败到这个次数后，在工具结果里附一句软提示。
#: 刻意只提示、不短路：部署者修好环境（例如换对 QQ 版本）之后继续调用必须
#: 真实执行，否则工具会永久不可用。
_TOOL_FAILURE_HINT_AFTER = 3
_MAX_TOOL_TEXT_CHARS = 16 * 1024
_MAX_TOOL_LOG_CHARS = 2 * 1024
_MAX_TOOL_REDACTION_CHARS = 1024 * 1024
_MAX_TOOL_REDACTION_ITEMS = 256
_SENSITIVE_TOOL_KEYS = frozenset(
    {
        "secret",
        "password",
        "passwd",
        "pwd",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
        "cookie",
        "credential",
        "access_key",
        "private_key",
        "bearer",
        "client_secret",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_TOOL_KEY_SUFFIXES = (
    "_secret",
    "_password",
    "_passwd",
    "_pwd",
    "_token",
    "_credential",
    "_authorization",
    "_cookie",
    "_api_key",
    "_access_key",
    "_private_key",
)
_INTERNAL_TOOL_KEYS = frozenset({"_delegate_context"})
def _normalize_tool_key(key: object) -> str:
    text = str(key)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").casefold()
def _is_sensitive_tool_key(key: object) -> bool:
    normalized = _normalize_tool_key(key)
    if normalized in _SENSITIVE_TOOL_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in _SENSITIVE_TOOL_KEY_SUFFIXES)
def _bounded_tool_text(value: object, limit: int = _MAX_TOOL_TEXT_CHARS) -> str:
    if isinstance(value, str):
        text = value[: limit + 1]
    elif isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=lambda _: "<object>")[
                : limit + 1
            ]
        except (TypeError, ValueError, RecursionError):
            text = f"<{type(value).__name__}>"
    else:
        try:
            text = str(value)[: limit + 1]
        except Exception:
            text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"
def _clip_tool_summary(text: str, limit: int) -> str:
    """压缩工具输出时保留的摘要:优先在换行处截断,避免半截 JSON 误导模型。"""
    cleaned = text.strip()
    if limit <= 0 or len(cleaned) <= limit:
        return cleaned
    head = cleaned[:limit]
    newline = head.rfind("\n")
    if newline >= limit // 2:
        head = head[:newline]
    return head.rstrip() + "..."
def _render_tool_result_template(
    template: str,
    *,
    tool_name: str,
    summary: str,
    original_chars: int,
) -> str:
    """渲染工具输出压缩模板(占位符与转义规则与其它提示词一致)。"""
    return render_template(
        template,
        {
            "tool_name": tool_name or "未知工具",
            "summary": summary,
            "original_chars": original_chars,
        },
    )
def _redact_tool_value(
    value: object,
    _depth: int = 0,
    *,
    drop_internal: bool = False,
) -> object:
    """递归替换敏感键的值；深/宽超限时整体折叠，避免无界展开。"""
    if _depth > 8:
        return "<truncated>"
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_TOOL_REDACTION_ITEMS:
                redacted["..."] = "<truncated>"
                break
            key_text = str(key)
            if key_text in _INTERNAL_TOOL_KEYS:
                if not drop_internal:
                    redacted[key_text] = "<redacted>"
                continue
            safe_key = _scrub_secret_values(key_text)
            redacted[safe_key] = (
                "<redacted>"
                if _is_sensitive_tool_key(key)
                else _redact_tool_value(
                    item,
                    _depth + 1,
                    drop_internal=drop_internal,
                )
            )
        return redacted
    if isinstance(value, (list, tuple)):
        items = list(value[:_MAX_TOOL_REDACTION_ITEMS])
        redacted_items = [
            _redact_tool_value(
                item,
                _depth + 1,
                drop_internal=drop_internal,
            )
            for item in items
        ]
        if len(value) > _MAX_TOOL_REDACTION_ITEMS:
            redacted_items.append("<truncated>")
        return redacted_items
    if isinstance(value, str):
        return _scrub_secret_values(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return "<object>"
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+|"
    r"[\"']?(?:authorization|api[_-]?key|apikey|access[_-]?token|access[_-]?key|"
    r"auth[_-]?token|client[_-]?secret|private[_-]?key|"
    r"secret|token|passwd|password|credential|pwd)"
    r"[\"']?\s*[:=]\s*[\"']?)"
    r"(?:bearer\s+)?[^\s,;\"']+"
)
#: 没有键名的裸密钥形态（``sk-proj-...``）：上面那条正则要求 ``key=value``
#: 或 ``Bearer``，异常文本里直接出现的 key 会整条漏给模型。
_BARE_SECRET_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
#: URL 内嵌凭据：``https://user:password@host``。
_URL_USERINFO_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
def _scrub_secret_values(text: str) -> str:
    """把字符串值内嵌的常见密钥形态（Bearer <token>、token=xxx 等）替换为占位符。"""
    if not isinstance(text, str):
        return text
    scrubbed = _SECRET_VALUE_RE.sub(lambda match: match.group(1) + "<redacted>", text)
    scrubbed = _BARE_SECRET_KEY_RE.sub("<redacted>", scrubbed)
    return _URL_USERINFO_RE.sub(r"\1<redacted>@", scrubbed)
def _redacted_tool_text(value: object, limit: int = _MAX_TOOL_LOG_CHARS) -> str:
    """日志/调试用文本：先解析完整的有界对象并脱敏，最后才截断。"""
    if isinstance(value, str):
        parsed: object | None = None
        should_parse = len(value) <= _MAX_TOOL_REDACTION_CHARS
        if should_parse:
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
                parsed = None
        if parsed is not None or value.strip() == "null":
            text = _bounded_tool_text(
                _redact_tool_value(parsed),
                _MAX_TOOL_REDACTION_CHARS,
            )
        else:
            # Only the prefix can reach the bounded log output. Scrub it before
            # truncating so oversized or malformed JSON cannot bypass redaction.
            scan_limit = max(_MAX_TOOL_TEXT_CHARS, limit * 2)
            text = _scrub_secret_values(value[:scan_limit])
    else:
        try:
            text = json.dumps(
                _redact_tool_value(value),
                ensure_ascii=False,
                default=lambda _: "<object>",
            )
        except (TypeError, ValueError, RecursionError):
            text = f"<{type(value).__name__}>"
    return _bounded_tool_text(_scrub_secret_values(text), limit)
def _safe_tool_args(args: object) -> str:
    redacted = _redact_tool_value(args, drop_internal=True)
    return _redacted_tool_text(redacted, _MAX_TOOL_LOG_CHARS)
def _render_tool_package_index(skill_manager: Any) -> str:
    """把可加载工具包 + 工具名直接渲染进提示词，省掉模型先查询/看说明的一次调用。"""
    if skill_manager is None:
        return ""
    names = getattr(skill_manager, "deferred_skill_names", None)
    tool_names = getattr(skill_manager, "skill_tool_names", None)
    if not names or not callable(tool_names):
        return ""
    lines: list[str] = []
    for name in names:
        tools = list(tool_names(name) or [])
        if tools:
            lines.append("- " + name + ": " + ", ".join(tools))
    return "\n".join(lines)
def _parse_tool_args(value: object) -> dict[str, Any]:
    """Normalize provider tool arguments to the dictionary executor contract."""
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}
