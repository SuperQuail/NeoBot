"""B站回复的发送工具：和 QQ 一样通过 send_reply 指定要发出的文本。"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import Any

from neobot_chat.schema.exceptions import ProviderError
from neobot_app.reply.postprocess import split_into_sentences_w_remove_punctuation

#: 单次模型调用超时上限；整轮仍受 timeout 约束（两次调用不会共用一个 60s）。
_CALL_TIMEOUT_SECONDS = 60.0
#: 循环上限：一轮正常 1~2 次调用，这里只防止模型持续调工具时死循环。
_MAX_ITERATIONS = 200
_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_hit_tokens", "cache_miss_tokens")


def _add_usage(usage: dict[str, int] | None, response: Any) -> dict[str, int] | None:
    """把单轮 usage 累加进本轮总量（每轮都要记，回复正文常在前几轮）。"""
    if not isinstance(response, dict):
        return usage
    value = (response.get("extensions") or {}).get("usage")
    if not isinstance(value, dict):
        return usage
    if usage is None:
        usage = {key: 0 for key in _USAGE_KEYS}
    for key in _USAGE_KEYS:
        usage[key] += int(value.get(key, 0) or 0)
    return usage


def _parse_tool_args(raw: Any) -> dict:
    """工具参数容错解析：JSON 字符串/对象都接受，坏参数按空对象处理。"""
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}

_SEND_REPLY = {
    "type": "function",
    "function": {
        "name": "send_reply",
        "description": "发送这条B站回复。必须调用它；直接输出的正文不会被发送。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 20000},
                "reply_to_uid": {
                    "type": "integer",
                    "description": "可选：要 @ 的观众 UID（直播间弹幕行首 [uid=...]；不是消息编号）；不传则不 @",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}
_CANCEL = {
    "type": "function",
    "function": {
        "name": "cancel",
        "description": "本轮不回复。只有确定不值得回复时才调用。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

#: 工具面：只有发送与取消，其余一律不暴露。
_TOOL_DEFS = (_SEND_REPLY, _CANCEL)
_TOOL_NAMES = frozenset(item["function"]["name"] for item in _TOOL_DEFS)


@dataclass
class ToolReply:
    text: str | None = None
    usage: dict[str, Any] | None = None
    segments: list[str] | None = None
    reply_to: int = 0
    #: 本轮实际发起的模型调用次数（= assistant 消息数），用于延迟/成本归因。
    iterations: int = 0


class _ReplyExecutor:
    def __init__(
        self, *, max_chars: int = 0, split: bool = False, allow_reply_to: bool = False
    ) -> None:
        self.max_chars = max(0, int(max_chars or 0))
        self.split = bool(split)
        self.allow_reply_to = bool(allow_reply_to)
        self.text: str | None = None
        self.reply_to = 0
        self.segments: list[str] | None = None
        self.cancelled = False

    def definitions(self) -> list[dict]:
        return [_SEND_REPLY, _CANCEL]

    async def execute(self, name: str, args: dict) -> str:
        if name == "cancel":
            self.cancelled = True
            self.text = None
            return '{"ok": true}'
        if name == "send_reply":
            text = str(args.get("text") or "").strip()
            if not text:
                return '{"ok": false, "error": "text 不能为空"}'
            if self.allow_reply_to:
                try:
                    self.reply_to = int(args.get("reply_to_uid", args.get("reply_to")) or 0)
                except (TypeError, ValueError):
                    self.reply_to = 0
            if text.upper() == "[SKIP]":
                self.cancelled = True
                self.text = None
                return '{"ok": true, "cancelled": true}'
            if self.split and self.max_chars:
                parts = [
                    part.strip()
                    for part in split_into_sentences_w_remove_punctuation(
                        text, rng=random.Random(0)
                    )
                    if part.strip()
                ]
                overlong = [part for part in parts if len(part) > self.max_chars]
                if not parts:
                    return '{"ok": false, "error": "弹幕为空，请重写"}'
                if overlong:
                    return (
                        '{"ok": false, "error": "B站弹幕每条最多'
                        + str(self.max_chars)
                        + '字，以下句子超长，请改短后再次调用 send_reply: '
                        + " / ".join(overlong)[:2000]
                        + '"}'
                    )
                self.segments = parts
                self.text = " ".join(parts)
                return '{"ok": true}'
            if self.max_chars and len(text) > self.max_chars:
                text = text[: self.max_chars]
            self.text = text
            return '{"ok": true}'
        return '{"ok": false, "error": "未知工具"}'

    async def close(self) -> None:
        return None


async def run_tool_reply(
    provider: Any,
    system: str,
    user: str = "",
    *,
    messages: list[dict[str, Any]] | None = None,
    max_chars: int = 0,
    split: bool = False,
    timeout: float = 90.0,
    allow_reply_to: bool = False,
    call_timeout: float = _CALL_TIMEOUT_SECONDS,
    max_iterations: int = _MAX_ITERATIONS,
) -> ToolReply:
    """跑一轮只含 send_reply/cancel 的模型循环，返回工具指定的回复。

    自己驱动循环、不用通用 Agent 外壳：system 就是调用方给的文本，单次调用与整轮
    各有超时，工具面只有发送与取消。messages 给定时按多轮对话发送（system 之外）。
    """
    if provider is None:
        return ToolReply()
    executor = _ReplyExecutor(
        max_chars=max_chars, split=split, allow_reply_to=allow_reply_to
    )
    conversation: list[dict[str, Any]] = [{"role": "system", "content": system}]
    conversation.extend(
        list(messages)
        if messages is not None
        else [{"role": "user", "content": user}]
    )
    deadline = time.monotonic() + max(0.0, timeout)
    usage: dict[str, int] | None = None
    iterations = 0

    async def _call_provider() -> Any:
        """provider 自身的异常统一包成 ProviderError（调用方按可重试处理）。"""
        try:
            return await provider.chat(conversation, tools=list(_TOOL_DEFS))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"{type(exc).__name__}: {exc}",
                provider=str(
                    getattr(provider, "registered_key", "")
                    or getattr(provider, "model", "")
                    or type(provider).__name__
                ),
                original=exc,
                iteration=iterations,
            ) from exc

    while iterations < max_iterations:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError("B站回复生成超过整轮时限")
        response = await asyncio.wait_for(
            _call_provider(),
            timeout=min(remaining, call_timeout),
        )
        iterations += 1
        conversation.append(response)
        usage = _add_usage(usage, response)
        tool_calls = response.get("tool_calls") if isinstance(response, dict) else None
        if not tool_calls:
            break
        for call in tool_calls:
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            if name in _TOOL_NAMES:
                result = await executor.execute(
                    name, _parse_tool_args(function.get("arguments"))
                )
            else:
                result = '{"ok": false, "error": "未知工具"}'
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or ""),
                    "name": name,
                    "content": result,
                }
            )
        if executor.cancelled:
            break
    return ToolReply(
        text=None if executor.cancelled else executor.text,
        usage=usage,
        segments=None if executor.cancelled else executor.segments,
        reply_to=0 if executor.cancelled else executor.reply_to,
        iterations=iterations,
    )
