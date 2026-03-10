from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypedDict


# ── 结构化类型定义 ──


class ToolFunction(TypedDict, total=False):
    """工具函数定义"""

    name: str
    arguments: str  # JSON 字符串


class ToolCall(TypedDict):
    """工具调用"""

    id: str
    type: Literal["function"]
    function: ToolFunction


class Message(TypedDict, total=False):
    """消息（支持 user/assistant/system/tool 角色）"""

    role: str
    content: str | None
    tool_calls: list[ToolCall]  # assistant 消息可能包含
    tool_call_id: str  # tool 消息必须包含


class ToolDefinition(TypedDict):
    """工具定义（OpenAI 格式）"""

    function: ToolFunctionSchema


class ToolFunctionSchema(TypedDict, total=False):
    """工具函数 schema"""

    name: str
    description: str
    parameters: dict  # JSON Schema


class State(TypedDict, total=False):
    """Agent 状态"""

    messages: list[Message]


# ── 回调和协议 ──

# 回调类型：on_event(event_type, data)
# event_type: "llm_start" | "llm_end" | "tool_start" | "tool_end" | "error"
OnEvent = Callable[[str, dict], None]


class Runnable(Protocol):
    async def invoke(self, state: State) -> State: ...


@dataclass
class ChatChunk:
    """流式响应块

    - delta: 本次文本增量（可为空）
    - message: 仅在流结束时设置，包含完整的 assistant 消息（Provider 层）
    - state: 仅在 Agent 流式调用结束时设置，包含完整状态（Agent 层）
    """

    delta: str = ""
    message: Message | None = field(default=None, repr=False)
    state: State | None = field(default=None, repr=False)
