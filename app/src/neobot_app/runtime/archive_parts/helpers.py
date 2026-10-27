"""档案自动总结的纯函数：冲刷结果消费、文本/工具返回截断、计数器消息规整。"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .constants import (
    AUTO_COMPRESSION_USAGE_KIND,
    DEFAULT_OVERFLOW_COOLDOWN_SECONDS,
    MANUAL_COMPRESSION_USAGE_KIND,
    MAX_OVERFLOW_PROMPT_CHARS,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOOL_RESULT_TOTAL_CHARS,
    _ARCHIVE_PROMPT_OMITTED,
    _TOOL_DROPPED_MARKER,
    _TOOL_FAILURE_MARKERS,
    _TOOL_TRUNCATED_MARKER,
)


def _tunable(name: str, default: Any) -> Any:
    """读取门面模块上的常量：测试/运行期会按模块属性覆盖阈值，拆分后必须仍然生效。"""
    facade = sys.modules.get("neobot_app.runtime.archive_memory_summary")
    if facade is None or not hasattr(facade, name):
        return default
    return getattr(facade, name)

def _consume_flush_result(task: asyncio.Task) -> None:
    """消费超预算后仍在跑的冲刷任务结果，避免异常无人取用。"""
    if task.cancelled():
        return
    try:
        task.exception()
    except Exception:
        pass

def _settled_flush_result(task: asyncio.Task) -> Any:
    """取一个已结束的冲刷任务结果；未结束/失败都视为「本次没刷新」。"""
    if not task.done() or task.cancelled():
        return None
    try:
        return task.result()
    except Exception:
        return None

def _unfinished_flush_count(tasks: list[asyncio.Task]) -> int:
    """仍未结束的冲刷任务数（超预算时用于如实上报，而不是假装刷完了）。"""
    return sum(1 for task in tasks if not task.done())

def _compression_usage_kind(source: str) -> str:
    """把压缩来源翻译成用量统计的 conversation_kind（手动与自动单列）。"""
    return (
        MANUAL_COMPRESSION_USAGE_KIND
        if str(source or "").strip() == "manual"
        else AUTO_COMPRESSION_USAGE_KIND
    )

def _positive_int_or_zero(value: Any) -> int:
    """配置读取：非负整数上限；None/非法值/负数一律视为 0（禁用）。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0

def _cooldown_seconds_or_default(value: Any, default: float = DEFAULT_OVERFLOW_COOLDOWN_SECONDS) -> float:
    """配置读取：冷却秒数；None/非法值回落默认值，0 表示不冷却。"""
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)

def _bounded_archive_text(value: str) -> str:
    """限制注入压缩提示词的档案长度：超长时保留首尾，中间省略。"""
    limit = _tunable("MAX_OVERFLOW_PROMPT_CHARS", MAX_OVERFLOW_PROMPT_CHARS)
    if len(value) <= limit:
        return value
    head_chars = limit // 2
    tail_chars = limit - head_chars
    return f"{value[:head_chars]}{_ARCHIVE_PROMPT_OMITTED}{value[-tail_chars:]}"

def _request_chars(messages: list[Any]) -> int:
    """估算一次请求的可见字符数(图片按固定额度计，不把 base64 当文本)。"""
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"image_url", "image", "file"}:
                    total += 3072
                else:
                    total += len(str(part.get("text", "")))
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            total += sum(len(str(item)) for item in tool_calls)
    return total

def _bounded_tool_result(result: Any) -> str:
    """限制单条工具返回的字符数。

    read_pending_messages / list_archive / read_archive 都会返回大块内容，
    而这些内容会被追加进 chat_messages 并在之后每一轮重新发送；
    不设上限时一次总结就能把上下文顶到几十万 token。
    """
    text = str(result or "")
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + _TOOL_TRUNCATED_MARKER

def _trim_tool_history(chat_messages: list[dict]) -> None:
    """从最新往旧保留工具返回，超出总量预算的早期工具返回替换为占位符。

    直接改写在原地进行，system / user / assistant 消息不受影响。
    """
    budget = MAX_TOOL_RESULT_TOTAL_CHARS
    for message in reversed(chat_messages):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        if content == _TOOL_DROPPED_MARKER:
            continue
        if budget - len(content) >= 0:
            budget -= len(content)
            continue
        message["content"] = _TOOL_DROPPED_MARKER

def _is_tool_failure(result: Any) -> bool:
    """判断工具结果是否属于失败（未知工具/执行异常/JSON ok=false）。"""
    text = str(result or "")
    if any(marker in text for marker in _TOOL_FAILURE_MARKERS):
        return True
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is False

def _normalize_message_text(text: str) -> str:
    return " ".join(str(text or "").split())

def _normalize_counter_message(message: Any) -> dict[str, str]:
    if isinstance(message, dict):
        return {
            "sender_id": str(message.get("sender_id") or ""),
            "sender_name": str(message.get("sender_name") or ""),
            "text": str(message.get("text") or ""),
        }
    return {"sender_id": "", "sender_name": "", "text": str(message)}

def _format_sender(item: dict[str, str]) -> str:
    sender_bits = []
    if item["sender_name"]:
        sender_bits.append(item["sender_name"])
    if item["sender_id"]:
        sender_bits.append(f"QQ:{item['sender_id']}")
    return " / ".join(sender_bits) or "未知发送者"

def _format_counter_message(message: Any) -> str:
    item = _normalize_counter_message(message)
    return f"{_format_sender(item)}: {item['text']}"
