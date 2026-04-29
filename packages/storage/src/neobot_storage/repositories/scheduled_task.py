"""SqlAlchemy scheduled task repository."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models import ConversationRef
from neobot_contracts.time_context import now_utc, to_utc
from neobot_contracts.models.scheduled_task import (
    CompletedScheduledTaskRecord,
    ScheduledTaskRecord,
    ScheduledTaskRecurrence,
    ScheduledTaskState,
)
from neobot_contracts.ports.scheduled_task_access import ScheduledTaskAccess

from neobot_storage.models import CompletedScheduledTaskData, ScheduledTaskData


class SqlAlchemyScheduledTaskAccess:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_uuid: str) -> ScheduledTaskRecord | None:
        row = await self._get_optional_row(task_uuid)
        return self._to_domain(row) if row is not None else None

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
    ) -> ScheduledTaskRecord:
        now = now_utc()
        row = ScheduledTaskData(
            task_uuid=task_uuid,
            title=title,
            detail=detail,
            recurrence=ScheduledTaskRecurrence(recurrence).value,
            start_at=self._normalize_datetime(start_at),
            end_at=self._normalize_datetime(end_at),
            bindings_json=self._dump_bindings(bindings),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            completed_window_keys_json="[]",
            state=ScheduledTaskState.ACTIVE.value,
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

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
    ) -> ScheduledTaskRecord:
        row = await self._get_row(task_uuid)
        if title is not None:
            row.title = title
        if detail is not None:
            row.detail = detail
        if recurrence is not None:
            row.recurrence = ScheduledTaskRecurrence(recurrence).value
        if start_at is not None:
            row.start_at = self._normalize_datetime(start_at)
        if end_at is not None:
            row.end_at = self._normalize_datetime(end_at)
        if bindings is not None:
            row.bindings_json = self._dump_bindings(bindings)
        if metadata is not None:
            row.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        if state is not None:
            row.state = ScheduledTaskState(state).value
        if completed_window_keys is not None:
            row.completed_window_keys_json = json.dumps(
                list(dict.fromkeys(str(item) for item in completed_window_keys)),
                ensure_ascii=False,
            )
        row.updated_at = now_utc()
        row.version += 1
        await self._session.flush()
        return self._to_domain(row)

    async def delete(self, task_uuid: str) -> bool:
        stmt = sql_delete(ScheduledTaskData).where(ScheduledTaskData.task_uuid == task_uuid)
        result = await self._session.execute(stmt)
        completed_stmt = sql_delete(CompletedScheduledTaskData).where(
            CompletedScheduledTaskData.task_uuid == task_uuid
        )
        completed_result = await self._session.execute(completed_stmt)
        await self._session.flush()
        return bool(result.rowcount or completed_result.rowcount)

    async def list_active(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ScheduledTaskRecord]:
        stmt = (
            select(ScheduledTaskData)
            .where(ScheduledTaskData.state == ScheduledTaskState.ACTIVE.value)
            .order_by(ScheduledTaskData.start_at.asc(), ScheduledTaskData.id.asc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list(
        self,
        *,
        include_disabled: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTaskRecord]:
        stmt = select(ScheduledTaskData)
        if not include_disabled:
            stmt = stmt.where(ScheduledTaskData.state == ScheduledTaskState.ACTIVE.value)
        stmt = (
            stmt.order_by(ScheduledTaskData.updated_at.desc(), ScheduledTaskData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def count_repeating_active(self) -> int:
        stmt = (
            select(func.count())
            .select_from(ScheduledTaskData)
            .where(ScheduledTaskData.state == ScheduledTaskState.ACTIVE.value)
            .where(ScheduledTaskData.recurrence != ScheduledTaskRecurrence.ONCE.value)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def archive_completed(
        self,
        task_uuid: str,
        *,
        completed_at: datetime,
        completion_reason: str,
    ) -> CompletedScheduledTaskRecord | None:
        row = await self._get_optional_row(task_uuid)
        if row is None:
            return None
        completed_at = self._normalize_datetime(completed_at)
        payload = self._scheduled_payload(row)
        archived = CompletedScheduledTaskData(
            task_uuid=row.task_uuid,
            title=row.title,
            detail=row.detail,
            recurrence=row.recurrence,
            start_at=row.start_at,
            end_at=row.end_at,
            bindings_json=row.bindings_json,
            metadata_json=row.metadata_json,
            completed_at=completed_at,
            completion_reason=completion_reason,
            archived_payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        self._session.add(archived)
        await self._session.delete(row)
        await self._session.flush()
        return self._to_completed_domain(archived)

    async def _get_optional_row(self, task_uuid: str) -> ScheduledTaskData | None:
        stmt = select(ScheduledTaskData).where(ScheduledTaskData.task_uuid == task_uuid)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, task_uuid: str) -> ScheduledTaskData:
        row = await self._get_optional_row(task_uuid)
        if row is None:
            raise LookupError(f"scheduled task not found for task_uuid={task_uuid}")
        return row

    @staticmethod
    def _dump_bindings(bindings: list[ConversationRef] | tuple[ConversationRef, ...]) -> str:
        return json.dumps(
            [{"kind": item.kind, "id": str(item.id)} for item in bindings],
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _load_bindings(raw: str) -> tuple[ConversationRef, ...]:
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError:
            data = []
        result: list[ConversationRef] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind") or "").strip()
                conv_id = str(item.get("id") or "").strip()
                if kind and conv_id:
                    result.append(ConversationRef(kind=kind, id=conv_id))
        return tuple(result)

    @staticmethod
    def _load_json_object(raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _load_json_list(raw: str) -> tuple[str, ...]:
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return ()
        if not isinstance(data, list):
            return ()
        return tuple(str(item) for item in data)

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        return to_utc(value)

    @classmethod
    def _to_domain(cls, row: ScheduledTaskData) -> ScheduledTaskRecord:
        return ScheduledTaskRecord(
            id=row.id,
            task_uuid=row.task_uuid,
            title=row.title,
            detail=row.detail,
            recurrence=ScheduledTaskRecurrence(row.recurrence),
            start_at=cls._normalize_datetime(row.start_at),
            end_at=cls._normalize_datetime(row.end_at),
            bindings=cls._load_bindings(row.bindings_json),
            metadata=cls._load_json_object(row.metadata_json),
            completed_window_keys=cls._load_json_list(row.completed_window_keys_json),
            state=ScheduledTaskState(row.state),
            created_at=cls._normalize_datetime(row.created_at),
            updated_at=cls._normalize_datetime(row.updated_at),
            version=row.version,
        )

    @classmethod
    def _to_completed_domain(cls, row: CompletedScheduledTaskData) -> CompletedScheduledTaskRecord:
        return CompletedScheduledTaskRecord(
            id=row.id,
            task_uuid=row.task_uuid,
            title=row.title,
            detail=row.detail,
            recurrence=ScheduledTaskRecurrence(row.recurrence),
            start_at=cls._normalize_datetime(row.start_at),
            end_at=cls._normalize_datetime(row.end_at),
            bindings=cls._load_bindings(row.bindings_json),
            metadata=cls._load_json_object(row.metadata_json),
            completed_at=cls._normalize_datetime(row.completed_at),
            completion_reason=row.completion_reason,
            archived_payload=cls._load_json_object(row.archived_payload_json),
        )

    @classmethod
    def _scheduled_payload(cls, row: ScheduledTaskData) -> dict[str, Any]:
        record = cls._to_domain(row)
        return {
            "task_uuid": record.task_uuid,
            "title": record.title,
            "detail": record.detail,
            "recurrence": record.recurrence.value,
            "start_at": record.start_at.isoformat(),
            "end_at": record.end_at.isoformat(),
            "bindings": [
                {"kind": item.kind, "id": str(item.id)}
                for item in record.bindings
            ],
            "metadata": record.metadata,
            "completed_window_keys": list(record.completed_window_keys),
            "state": record.state.value,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "version": record.version,
        }


_: ScheduledTaskAccess = SqlAlchemyScheduledTaskAccess  # type: ignore
