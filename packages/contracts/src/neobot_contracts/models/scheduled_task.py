"""Scheduled task domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from neobot_contracts.models.base import ConversationRef
from neobot_contracts.time_context import now_utc


class ScheduledTaskRecurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ScheduledTaskState(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ScheduledTaskRecord:
    id: int
    task_uuid: str
    title: str
    detail: str
    recurrence: ScheduledTaskRecurrence
    start_at: datetime
    end_at: datetime
    bindings: tuple[ConversationRef, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_window_keys: tuple[str, ...] = ()
    state: ScheduledTaskState = ScheduledTaskState.ACTIVE
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    version: int = 1


@dataclass(frozen=True, slots=True)
class CompletedScheduledTaskRecord:
    id: int
    task_uuid: str
    title: str
    detail: str
    recurrence: ScheduledTaskRecurrence
    start_at: datetime
    end_at: datetime
    bindings: tuple[ConversationRef, ...]
    metadata: dict[str, Any]
    completed_at: datetime
    completion_reason: str
    archived_payload: dict[str, Any]
