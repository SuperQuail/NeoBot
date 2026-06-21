"""DrawTask data structure for background drawing jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neobot_app.time_context import monotonic_seconds


@dataclass
class DrawTask:
    """Background drawing task record."""

    task_id: str
    pipeline_key: str
    conversation_kind: str
    conversation_id: str
    prompt: str
    requester: str = ""
    requirements: str = ""
    references: list[str] | None = None
    reference_id: int | None = None
    negative_prompt: str | None = None
    image_size: str | None = None
    seed: int | None = None
    status: str = "drawing"
    image_id: str | None = None
    error: str | None = None
    record_payload: dict[str, Any] | None = None
    notification_count: int = 0
    notified: bool = False
    created_at: float = field(default_factory=monotonic_seconds)
