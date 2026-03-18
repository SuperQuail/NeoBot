from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict


class ToolFunction(TypedDict):
    name: str
    arguments: str


class ToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: ToolFunction


MessageContent: TypeAlias = str | dict[str, Any] | list[dict[str, Any]] | None


class Message(TypedDict, total=False):
    role: str
    content: MessageContent
    extensions: dict[str, Any]
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
ToolAccessAction = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class ToolGuardContext:
    cwd: Path | None = None
    allowed_paths: list[Path] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolAccessRule:
    action: ToolAccessAction = "allow"
    fallback_action: ToolAccessAction | None = None


@dataclass(frozen=True)
class ToolAccessPolicy:
    default_rule: ToolAccessRule = field(default_factory=ToolAccessRule)
    list_agents_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="allow")
    )
    delegate_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="ask", fallback_action="allow")
    )
    path_in_scope_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="allow")
    )
    path_out_of_scope_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="ask", fallback_action="deny")
    )
    command_allowed_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="allow")
    )
    command_disallowed_rule: ToolAccessRule = field(
        default_factory=lambda: ToolAccessRule(action="ask", fallback_action="deny")
    )


@dataclass
class ChatChunk:
    delta: str = ""
    reasoning_delta: str = ""
    message: Message | None = field(default=None, repr=False)
    state: State | None = field(default=None, repr=False)
