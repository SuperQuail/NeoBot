from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


def validate_plugin_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        raise ValueError(f"invalid plugin name: {name!r}")
    return name


def validate_agent_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError(f"invalid agent name: {name!r}")
    return name


def validate_parse_error(value: str) -> None:
    if value not in {"ignore", "reply", "raise"}:
        raise ValueError("parse_error must be 'ignore', 'reply', or 'raise'")


def looks_like_context(value: Any) -> bool:
    return hasattr(value, "plugin_name") and hasattr(value, "hook_bus")

