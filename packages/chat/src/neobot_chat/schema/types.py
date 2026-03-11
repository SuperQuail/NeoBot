from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict


class ToolFunction(TypedDict):
    name: str
    arguments: str


class ToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: ToolFunction


class Message(TypedDict, total=False):
    role: str
    content: str | None
    tool_calls: list[ToolCall]
    tool_call_id: str


class ToolDefinition(TypedDict):
    type: Literal["function"]
    function: ToolFunctionSchema


class ToolFunctionSchema(TypedDict):
    name: str
    parameters: dict
    description: NotRequired[str]


class State(TypedDict, total=False):
    messages: list[Message]
    _matched_skills: list[object]


OnEvent = Callable[[str, dict], None]


@dataclass
class ChatChunk:
    delta: str = ""
    message: Message | None = field(default=None, repr=False)
    state: State | None = field(default=None, repr=False)
