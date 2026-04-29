"""Scheduled task persistence access port."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence, ScheduledTaskState

if TYPE_CHECKING:
    from neobot_contracts.models.scheduled_task import (
        CompletedScheduledTaskRecord,
        ScheduledTaskRecord,
    )


@runtime_checkable
class ScheduledTaskAccess(Protocol):
    async def get(self, task_uuid: str) -> ScheduledTaskRecord | None: ...

    async def create(
        self,
        *,
        task_uuid: str,
        title: str,
        detail: str,
        recurrence: ScheduledTaskRecurrence | str,
        start_at: datetime,
        end_at: datetime,
        bindings: list[ConversationRef] | tuple[ConversationRef, ...],
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTaskRecord: ...

    async def update(
        self,
        task_uuid: str,
        *,
        title: str | None = None,
        detail: str | None = None,
        recurrence: ScheduledTaskRecurrence | str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        bindings: list[ConversationRef] | tuple[ConversationRef, ...] | None = None,
        metadata: dict[str, Any] | None = None,
        state: ScheduledTaskState | str | None = None,
        completed_window_keys: list[str] | tuple[str, ...] | None = None,
    ) -> ScheduledTaskRecord: ...

    async def delete(self, task_uuid: str) -> bool: ...

    async def list_active(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ScheduledTaskRecord]: ...

    async def list(
        self,
        *,
        include_disabled: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTaskRecord]: ...

    async def count_repeating_active(self) -> int: ...

    async def archive_completed(
        self,
        task_uuid: str,
        *,
        completed_at: datetime,
        completion_reason: str,
    ) -> CompletedScheduledTaskRecord | None: ...
