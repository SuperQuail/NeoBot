from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from neobot_modloader.command_dsl import MessagePattern


Handler = Callable[..., Any]


@dataclass(slots=True)
class HandlerRegistration:
    kind: str
    pattern: MessagePattern
    handler: Handler
    priority: int
    block: bool
    block_ai_reply: bool
    timeout: float | None
    parse_error: str
    group: bool = False
    private: bool = False
    text: str | None = None
    contains: str | Sequence[str] | None = None
    keywords: str | Sequence[str] | None = None
    regex: str | re.Pattern[str] | None = None
    startswith: str | None = None
    endswith: str | None = None
    fullmatch: str | None = None
    rule: Callable[[dict[str, Any]], Any] | None = None


@dataclass(slots=True)
class AgentRegistration:
    name: str
    description: str
    handler: Handler
    factory: bool
    tools: list[dict[str, Any]] | None


@dataclass(slots=True)
class ToolRegistration:
    name: str
    description: str
    handler: Handler
    parameters: dict[str, Any] | None


def validate_plugin_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        raise ValueError(f"invalid plugin name: {name!r}")
    if name in {".", ".."} or any(
        path.is_absolute() or path.drive or len(path.parts) != 1 or path.name != name
        for path in (PurePosixPath(name), PureWindowsPath(name))
    ):
        raise ValueError(f"invalid plugin name: {name!r} (must be a single path-safe component)")
    if "__" in name:
        # `__` 与工具命名空间分隔符（{plugin}__{tool}）冲突，
        # 最终全局名必然含 `__` 被 bind_tools 拒绝，这里尽早报错
        raise ValueError(
            f"invalid plugin name: {name!r} (must not contain '__': "
            f"conflicts with the tool namespace separator)"
        )
    return name


def validate_agent_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError(f"invalid agent name: {name!r}")
    return name


def validate_tool_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name)
        or "__" in name
    ):
        raise ValueError(f"invalid tool name: {name!r}")
    return name


_QUALIFIED_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_qualified_tool_name(plugin_name: str, tool_name: str) -> str:
    """校验注册进宿主的最终工具全局名 ``{plugin}__{tool}``。

    插件名允许 ``.``（validate_plugin_name），但最终名发给 OpenAI/Anthropic
    时字符集不含点且总长不得超过 64，否则整个请求会被拒绝。
    """
    qualified = f"{plugin_name}__{tool_name}"
    if not isinstance(qualified, str) or not _QUALIFIED_TOOL_NAME_RE.fullmatch(qualified):
        raise ValueError(
            f"invalid qualified tool name: {qualified!r} "
            f"(plugin name {plugin_name!r} + tool name {tool_name!r})"
        )
    return qualified


def validate_parse_error(value: str) -> None:
    if value not in {"ignore", "reply", "raise"}:
        raise ValueError("parse_error must be 'ignore', 'reply', or 'raise'")


def looks_like_context(value: Any) -> bool:
    return hasattr(value, "plugin_name") and hasattr(value, "hook_bus")

