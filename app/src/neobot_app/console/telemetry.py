"""Small, bounded runtime snapshot store used by the built-in console."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from neobot_app.console.security import redact


class ConsoleTelemetry:
    """Capture recent model calls without retaining an unbounded chat history."""

    def __init__(self, max_calls: int = 100) -> None:
        self._calls: deque[dict[str, Any]] = deque(maxlen=max(10, max_calls))

    async def capture(self, envelope: Any) -> None:
        if getattr(envelope, "kind", "") != "reply_lifecycle":
            return
        if getattr(envelope, "stage", "") != "model.call.after":
            return
        payload = getattr(envelope, "payload", {})
        context = getattr(envelope, "context", {})
        self._calls.appendleft(
            {
                "captured_at": datetime.now(UTC).isoformat(),
                "event_id": str(context.get("event_id", "")),
                "target": getattr(envelope, "target", None),
                "mode": str(context.get("mode", "")),
                "iteration": payload.get("iteration"),
                "input": self._safe(payload.get("messages", [])),
                "output": self._safe(payload.get("response")),
            }
        )

    def snapshot(self, limit: int = 30) -> list[dict[str, Any]]:
        return list(self._calls)[: max(1, min(100, limit))]

    @classmethod
    def _safe(cls, value: Any, depth: int = 0) -> Any:
        if depth > 7:
            return "<内容层级过深>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value if len(value) <= 20000 else value[:20000] + "…"
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            result = {
                str(key): cls._safe(item, depth + 1)
                for key, item in list(value.items())[:100]
            }
            return redact(result)
        if isinstance(value, (list, tuple, set, deque)):
            return [cls._safe(item, depth + 1) for item in list(value)[:100]]
        if hasattr(value, "model_dump"):
            try:
                return cls._safe(value.model_dump(), depth + 1)
            except Exception:
                pass
        return cls._safe(str(value), depth + 1)
