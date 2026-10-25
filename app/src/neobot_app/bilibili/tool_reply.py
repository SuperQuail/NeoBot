"""B站回复的发送工具：和 QQ 一样通过 send_reply 指定要发出的文本。"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

from neobot_chat import Agent
from neobot_chat.schema.types import ToolAccessRule
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_app.reply.postprocess import split_into_sentences_w_remove_punctuation

_SEND_REPLY = {
    "type": "function",
    "function": {
        "name": "send_reply",
        "description": "发送这条B站回复。必须调用它；直接输出的正文不会被发送。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 20000},
                "reply_to": {
                    "type": "integer",
                    "description": "可选：要 @ 的观众 UID（直播间弹幕行首 [uid=...]）；不传则不 @",
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


@dataclass
class ToolReply:
    text: str | None = None
    usage: dict[str, Any] | None = None
    segments: list[str] | None = None
    reply_to: int = 0


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
                    self.reply_to = int(args.get("reply_to") or 0)
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
    user: str,
    *,
    max_chars: int = 0,
    split: bool = False,
    timeout: float = 90.0,
    allow_reply_to: bool = False,
) -> ToolReply:
    """跑一轮只含 send_reply/cancel 的 agent 循环，返回工具指定的回复。"""
    if provider is None:
        return ToolReply()
    executor = _ReplyExecutor(
        max_chars=max_chars, split=split, allow_reply_to=allow_reply_to
    )
    toolset = Toolset(
        executor=executor,
        specs=[
            ToolSpec(_SEND_REPLY, lambda *_: ToolAccessRule(action="allow")),
            ToolSpec(_CANCEL, lambda *_: ToolAccessRule(action="allow")),
        ],
    )
    agent = Agent(
        provider,
        toolset=toolset,
        include_builtin_tools=False,
        max_iterations=200,
        system_prompt=system,
    )
    state = await asyncio.wait_for(
        agent.invoke({"messages": [{"role": "user", "content": user}]}),
        timeout=timeout,
    )
    usage = None
    # 取最后一条带 usage 的 assistant 消息：末尾消息可能只有工具调用，没有用量。
    for message in reversed(state.get("messages", [])):
        if message.get("role") != "assistant":
            continue
        value = (message.get("extensions") or {}).get("usage")
        if isinstance(value, dict):
            usage = value
            break
    return ToolReply(
        text=None if executor.cancelled else executor.text,
        usage=usage,
        segments=None if executor.cancelled else executor.segments,
        reply_to=0 if executor.cancelled else executor.reply_to,
    )
