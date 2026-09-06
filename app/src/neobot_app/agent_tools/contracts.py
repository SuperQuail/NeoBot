"""Trusted invocation context and JSON tool contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Minted by the host adapter, never constructed from model arguments."""

    owner: str
    chat_flow_id: str
    user_id: int | None = None
    agent_id: str = "main"
    parent_agent_id: str | None = None
    depth: int = 0
    human_request: bool = False
    allowed_tools: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not self.owner or not self.chat_flow_id or ":" not in self.chat_flow_id:
            raise ValueError("A trusted owner and canonical chat flow are required")
        if self.depth < 0:
            raise ValueError("depth must be non-negative")


class AgentToolError(Exception):
    """A program-observable tool failure with a stable code."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def tool_definition(
    name: str, description: str, properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name, "description": description,
            "parameters": {
                "type": "object", "properties": properties or {},
                "required": required or [], "additionalProperties": False,
            },
        },
    }
