from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EventContext:
    raw_event: dict[str, Any]
    consumed: bool = False
    skip_ai_reply: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def post_type(self) -> str | None:
        value = self.raw_event.get("post_type")
        return str(value) if value is not None else None

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True
