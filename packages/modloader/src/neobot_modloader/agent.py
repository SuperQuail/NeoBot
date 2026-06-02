from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRequest:
    task: str
    messages: list[dict[str, Any]]
    delegate_context: str
    state: dict[str, Any]
