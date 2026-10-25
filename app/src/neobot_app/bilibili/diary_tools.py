"""B站日记 agent：工具化读取当天群聊摘要并提交动态。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from neobot_chat import Agent
from neobot_chat.schema.types import ToolAccessRule
from neobot_chat.tools.toolset import ToolSpec, Toolset

_READ = {
    "type": "function",
    "function": {
        "name": "read_diary_material",
        "description": "读取今天的群聊摘要。offset=0 从开头，正数向后翻页；每行前缀 + 表示今天新增/变化。",
        "parameters": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
            "additionalProperties": False,
        },
    },
}
_SEND = {
    "type": "function",
    "function": {
        "name": "send_dynamic",
        "description": "提交今天的B站动态正文。必须调用它；直接输出的正文不会被发布。",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 20000}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}
_CANCEL = {
    "type": "function",
    "function": {
        "name": "cancel",
        "description": "今天没有值得写的内容时不发动态。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


@dataclass
class DiaryResult:
    text: str | None = None


class _Executor:
    def __init__(self, lines: list[str], *, max_chars: int) -> None:
        self.lines = list(lines)
        self.max_chars = max(1, int(max_chars))
        self.text: str | None = None
        self.cancelled = False

    def definitions(self) -> list[dict]:
        return [_READ, _SEND, _CANCEL]

    async def execute(self, name: str, args: dict) -> str:
        if name == "read_diary_material":
            offset = max(0, int(args.get("offset") or 0))
            limit = max(1, min(int(args.get("limit") or 20), 50))
            page = self.lines[offset : offset + limit]
            return json.dumps(
                {
                    "ok": True,
                    "offset": offset,
                    "limit": limit,
                    "total": len(self.lines),
                    "has_more": offset + limit < len(self.lines),
                    "lines": page,
                },
                ensure_ascii=False,
            )
        if name == "cancel":
            self.cancelled = True
            self.text = None
            return '{"ok": true}'
        if name == "send_dynamic":
            text = str(args.get("text") or "").strip()
            if not text:
                return '{"ok": false, "error": "text 不能为空"}'
            if len(text) > self.max_chars:
                # 和 system 里的 <长度> 规则保持同一上限：超长让模型压缩重提，
                # 不要静默截断（截断会把结尾半句话发出去）。
                return json.dumps(
                    {
                        "ok": False,
                        "error": f"动态正文 {len(text)} 字，超过 {self.max_chars} 字上限，"
                        "请压缩后再次调用 send_dynamic",
                    },
                    ensure_ascii=False,
                )
            self.text = text
            return '{"ok": true}'
        return '{"ok": false, "error": "未知工具"}'

    async def close(self) -> None:
        return None


async def run_diary_agent(
    provider: Any,
    system: str,
    user: str,
    material: list[str],
    *,
    max_chars: int,
    timeout: float = 90.0,
) -> DiaryResult:
    executor = _Executor(material, max_chars=max_chars)
    toolset = Toolset(
        executor=executor,
        specs=[
            ToolSpec(_READ, lambda *_: ToolAccessRule(action="allow")),
            ToolSpec(_SEND, lambda *_: ToolAccessRule(action="allow")),
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
    await asyncio.wait_for(
        agent.invoke({"messages": [{"role": "user", "content": user}]}),
        timeout=timeout,
    )
    return DiaryResult(text=None if executor.cancelled else executor.text)
