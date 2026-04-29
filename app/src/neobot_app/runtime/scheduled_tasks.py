"""Scheduled task reminder runtime.

This module provides the dormant runtime manager used by the scheduled-task
agent.  It is not wired into application startup yet, but it already uses the
database-backed scheduled task repository and can be enabled later without
changing the agent or storage contracts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from typing import Any
from uuid import uuid4

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import (
    ScheduledTaskRecord,
    ScheduledTaskRecurrence,
    ScheduledTaskState,
)
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory
from neobot_app.time_context import now_utc, to_utc


@dataclass(frozen=True)
class ScheduledTaskConfig:
    enabled: bool = True
    reminder_cooldown_seconds: int = 300
    poll_interval_seconds: int = 60
    default_window_seconds: int = 3600
    max_repeating_tasks: int = 15
    default_one_shot_notification: bool = True

    @classmethod
    def from_schema(cls, config: Any | None) -> "ScheduledTaskConfig":
        if config is None:
            return cls()
        return cls(
            enabled=bool(getattr(config, "enabled", True)),
            reminder_cooldown_seconds=max(
                int(getattr(config, "reminder_cooldown_seconds", 300) or 300),
                1,
            ),
            poll_interval_seconds=max(
                int(getattr(config, "poll_interval_seconds", 60) or 60),
                1,
            ),
            default_window_seconds=max(
                int(getattr(config, "default_window_seconds", 3600) or 3600),
                1,
            ),
            max_repeating_tasks=max(
                int(getattr(config, "max_repeating_tasks", 15) or 15),
                0,
            ),
            default_one_shot_notification=bool(
                getattr(config, "default_one_shot_notification", True)
            ),
        )


@dataclass(frozen=True)
class ScheduledTaskWindow:
    key: str
    start: datetime
    end: datetime

    def contains(self, now: datetime) -> bool:
        return self.start <= now < self.end


class ScheduledTaskManager:
    """Database-backed reminder scanner for scheduled tasks."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory | None = None,
        config: ScheduledTaskConfig | None = None,
        logger: Logger | None = None,
        notification_hub: Any = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._config = config or ScheduledTaskConfig()
        self._logger = logger or NullLogger()
        self._notification_queues: dict[str, asyncio.Queue[str]] = {}
        self._last_reminder_at: dict[tuple[str, str], datetime] = {}
        self._reminder_attempts: dict[tuple[str, str, str], int] = {}
        self._orchestrator: Any = None
        self._notification_hub = notification_hub
        self._runner: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._config.enabled and self._uow_factory is not None

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
        if self._notification_hub is not None:
            self._notification_hub.set_orchestrator(orchestrator)

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    async def create_task(
        self,
        *,
        title: str,
        detail: str,
        recurrence: ScheduledTaskRecurrence | str,
        start_at: datetime,
        end_at: datetime,
        bindings: list[ConversationRef] | tuple[ConversationRef, ...],
        metadata: dict[str, Any] | None = None,
        task_uuid: str | None = None,
    ) -> ScheduledTaskRecord:
        self._require_storage()
        recurrence = ScheduledTaskRecurrence(recurrence)
        if recurrence != ScheduledTaskRecurrence.ONCE:
            async with self._uow_factory() as uow:
                count = await uow.scheduled_tasks.count_repeating_active()
            if count >= self._config.max_repeating_tasks:
                raise ValueError(
                    f"active repeating scheduled task limit reached: {self._config.max_repeating_tasks}"
                )
        async with self._uow_factory() as uow:
            task = await uow.scheduled_tasks.create(
                task_uuid=task_uuid or str(uuid4()),
                title=title,
                detail=detail,
                recurrence=recurrence,
                start_at=_normalize_datetime(start_at),
                end_at=_normalize_datetime(end_at),
                bindings=tuple(bindings),
                metadata=self._with_default_notification_policy(metadata),
            )
            await uow.commit()
            return task

    async def mark_completed(self, task_uuid: str) -> dict[str, Any]:
        self._require_storage()
        now = now_utc()
        async with self._uow_factory() as uow:
            task = await uow.scheduled_tasks.get(task_uuid)
            if task is None:
                return {"ok": False, "error": "scheduled task not found", "task_id": task_uuid}
            window = self._current_window(task, now)
            if task.recurrence == ScheduledTaskRecurrence.ONCE:
                archived = await uow.scheduled_tasks.archive_completed(
                    task.task_uuid,
                    completed_at=now,
                    completion_reason="marked_completed",
                )
                await uow.commit()
                return {
                    "ok": archived is not None,
                    "status": "completed",
                    "task_id": task.task_uuid,
                    "completed_at": now.isoformat(),
                }
            completed_keys = list(task.completed_window_keys)
            if window is not None and window.key not in completed_keys:
                completed_keys.append(window.key)
            updated = await uow.scheduled_tasks.update(
                task.task_uuid,
                completed_window_keys=completed_keys,
            )
            await uow.commit()
            return {
                "ok": True,
                "status": updated.state.value,
                "task_id": updated.task_uuid,
                "completed_window_key": window.key if window else None,
            }

    def get_pipeline_status(self, pipeline_key: str) -> dict[str, Any]:
        # This method is intentionally sync because reply tools currently expose
        # background status synchronously.  Runtime DB lookups are available via
        # the scheduled-task agent; this returns queue/cooldown state only.
        if self._notification_hub is not None:
            status = self._notification_hub.get_pipeline_status(pipeline_key)
            by_source = status.get("background_notifications_by_source", {})
            return {
                "scheduled_task_notifications_pending": by_source.get("scheduled_task", 0)
            }
        return {
            "scheduled_task_notifications_pending": (
                self._notification_queues.get(pipeline_key).qsize()
                if pipeline_key in self._notification_queues
                else 0
            )
        }

    async def start(self) -> None:
        if not self.enabled:
            self._logger.info("Scheduled task manager is disabled")
            return
        if self._runner is not None and not self._runner.done():
            return
        self._stopping.clear()
        self._runner = asyncio.create_task(self._run_loop())
        self._logger.info("Scheduled task manager started")

    async def shutdown(self) -> None:
        self._stopping.set()
        if self._runner is not None:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
        self._notification_queues.clear()
        self._last_reminder_at.clear()
        self._reminder_attempts.clear()
        self._logger.info("Scheduled task manager stopped")

    async def poll_notification(self, pipeline_key: str) -> str | None:
        if self._notification_hub is not None:
            notification = await self._notification_hub.poll(pipeline_key, source="scheduled_task")
            if notification is None:
                return None
            return notification.content

        queue = self._notification_queues.get(pipeline_key)
        if queue is None or queue.empty():
            return None
        try:
            notification = queue.get_nowait()
            self._logger.info(
                "Scheduled task notification polled",
                pipeline_key=pipeline_key,
                notification_preview=notification[:120],
            )
            return notification
        except asyncio.QueueEmpty:
            return None

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.scan_due_tasks()
            except Exception as exc:
                self._logger.warning("Scheduled task scan failed", error=str(exc))
            await asyncio.sleep(self._config.poll_interval_seconds)

    async def scan_due_tasks(self, now: datetime | None = None) -> None:
        self._require_storage()
        now = _normalize_datetime(now or now_utc())
        async with self._uow_factory() as uow:
            tasks = await uow.scheduled_tasks.list_active(limit=500)
            for task in tasks:
                if task.recurrence == ScheduledTaskRecurrence.ONCE and now >= task.end_at:
                    await uow.scheduled_tasks.archive_completed(
                        task.task_uuid,
                        completed_at=now,
                        completion_reason="expired_auto_completed",
                    )
                    continue
                window = self._current_window(task, now)
                if window is None:
                    continue
                if now >= window.end:
                    if (
                        task.recurrence != ScheduledTaskRecurrence.ONCE
                        and window.key not in task.completed_window_keys
                    ):
                        await uow.scheduled_tasks.update(
                            task.task_uuid,
                            completed_window_keys=[*task.completed_window_keys, window.key],
                        )
                    continue
                if not window.contains(now):
                    continue
                if window.key in task.completed_window_keys:
                    continue
                notified = False
                for binding in task.bindings:
                    notified = (
                        await self._remind_if_due(task, binding, window, now)
                        or notified
                    )
                if notified and self._is_one_shot_notification(task):
                    if task.recurrence == ScheduledTaskRecurrence.ONCE:
                        await uow.scheduled_tasks.archive_completed(
                            task.task_uuid,
                            completed_at=now,
                            completion_reason="one_shot_notification_sent",
                        )
                    else:
                        await uow.scheduled_tasks.update(
                            task.task_uuid,
                            completed_window_keys=[*task.completed_window_keys, window.key],
                        )
            await uow.commit()

    async def _remind_if_due(
        self,
        task: ScheduledTaskRecord,
        binding: ConversationRef,
        window: ScheduledTaskWindow,
        now: datetime,
    ) -> bool:
        pipeline_key = f"{binding.kind}:{binding.id}"
        reminder_key = (task.task_uuid, pipeline_key)
        last_at = self._last_reminder_at.get(reminder_key)
        if last_at is not None:
            elapsed = (now - last_at).total_seconds()
            if elapsed < self._config.reminder_cooldown_seconds:
                return False
        self._last_reminder_at[reminder_key] = now
        attempt_key = (task.task_uuid, window.key, pipeline_key)
        attempt = self._reminder_attempts.get(attempt_key, 0) + 1
        self._reminder_attempts[attempt_key] = attempt
        prompt = self._build_reminder_prompt(task, binding, window, attempt)

        if self._notification_hub is not None:
            await self._notification_hub.publish(
                source="scheduled_task",
                kind=binding.kind,
                conversation_id=str(binding.id),
                content=prompt,
                manager_name="scheduled_task",
                reasons=["scheduled task reminder"],
                metadata={"task_uuid": task.task_uuid, "window_key": window.key},
            )
            return True

        if self._orchestrator is not None:
            active = getattr(self._orchestrator, "_active_pipelines", {})
            active_reply = active.get(pipeline_key)
            pipeline_active = active_reply is not None and not active_reply.done()
            if not pipeline_active:
                try:
                    result = self._orchestrator.start_background_reply(
                        kind=binding.kind,
                        conversation_id=str(binding.id),
                        content=prompt,
                        manager_name="scheduled_task",
                        reasons=["scheduled task reminder"],
                    )
                    if result is not None:
                        return True
                except Exception as exc:
                    self._logger.warning(
                        "Scheduled task background reply failed",
                        task_id=task.task_uuid,
                        pipeline_key=pipeline_key,
                        error=str(exc),
                    )

        queue = self._notification_queues.setdefault(pipeline_key, asyncio.Queue())
        await queue.put(prompt)
        self._logger.info(
            "Scheduled task reminder queued",
            task_id=task.task_uuid,
            pipeline_key=pipeline_key,
        )
        return True

    def _build_reminder_prompt(
        self,
        task: ScheduledTaskRecord,
        binding: ConversationRef,
        window: ScheduledTaskWindow,
        attempt: int = 1,
    ) -> str:
        detail = f"\n任务详情：{task.detail}" if task.detail else ""
        one_shot = self._is_one_shot_notification(task)
        completion_instruction = (
            "本任务配置为一次性通知：系统在本次通知发出后已自动完成当前触发窗口。"
            "你只需要在绑定聊天流中发送提醒或祝福消息；不要再调用 mark_scheduled_task_complete，除非用户明确要求手动结束整个任务。\n"
            if one_shot
            else (
                "本任务配置为持续通知：对于提醒任务和生日祝福任务，只需要在绑定聊天流中发送提醒或祝福消息即可；"
                "发送后必须调用 mark_scheduled_task_complete，并使用上面的任务 UUID 标记完成。\n"
                "对于持续提醒类任务，如果已经提醒三到五次仍然没有用户反馈，请发送一次自然的最终提醒，然后调用 mark_scheduled_task_complete 结束本次任务。\n"
                "如果用户已经明确表示任务完成，或你判断提醒事项已经处理完，也要调用 mark_scheduled_task_complete 标记完成。\n"
            )
        )
        metadata = (
            "\n任务元数据："
            + json.dumps(task.metadata, ensure_ascii=False, sort_keys=True)
            if task.metadata
            else ""
        )
        return (
            "<新的必须回复内容>\n"
            "这是一条定时任务提醒，不是用户的新请求。\n"
            f"任务 UUID：{task.task_uuid}\n"
            f"任务标题：{task.title}{detail}{metadata}\n"
            f"绑定聊天流：{binding.kind}:{binding.id}\n"
            f"触发时间窗口：{window.start.isoformat()} 至 {window.end.isoformat()}\n"
            f"当前绑定聊天流在本次触发窗口内的提醒次数：第 {attempt} 次。\n"
            f"通知策略：{'一次性通知' if one_shot else '持续通知'}。一次性通知不是 once 一次性任务；daily/yearly 等循环任务也可以在每个循环窗口内只通知一次。\n"
            f"{completion_instruction}"
            "如果任务在完成前仍需要进一步动作，则先在绑定聊天流中自然提醒。\n"
            "</新的必须回复内容>"
        )

    def _is_one_shot_notification(self, task: ScheduledTaskRecord) -> bool:
        value = task.metadata.get("one_shot_notification")
        if value is None:
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().casefold()
        if text in {"true", "1", "yes", "on", "enabled", "enable"}:
            return True
        if text in {"false", "0", "no", "off", "disabled", "disable"}:
            return False
        return True

    def _with_default_notification_policy(
        self,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = dict(metadata or {})
        result.setdefault(
            "one_shot_notification",
            self._config.default_one_shot_notification,
        )
        return result

    def _current_window(
        self,
        task: ScheduledTaskRecord,
        now: datetime,
    ) -> ScheduledTaskWindow | None:
        if task.state != ScheduledTaskState.ACTIVE:
            return None
        start = _occurrence_start(task, now)
        if start is None:
            return None
        duration = max((task.end_at - task.start_at).total_seconds(), 1)
        end = start + timedelta(seconds=duration)
        return ScheduledTaskWindow(
            key=f"{task.task_uuid}:{start.isoformat()}",
            start=start,
            end=end,
        )

    def _require_storage(self) -> None:
        if self._uow_factory is None:
            raise RuntimeError("scheduled task storage is not configured")


def _occurrence_start(task: ScheduledTaskRecord, now: datetime) -> datetime | None:
    start_at = _normalize_datetime(task.start_at)
    end_at = _normalize_datetime(task.end_at)
    now = _normalize_datetime(now)
    if end_at <= start_at:
        return None
    if task.recurrence == ScheduledTaskRecurrence.ONCE:
        return start_at
    if now < start_at:
        return None
    if task.recurrence == ScheduledTaskRecurrence.DAILY:
        return _combine_date_time(now.date(), start_at)
    if task.recurrence == ScheduledTaskRecurrence.WEEKLY:
        days_since = (now.date() - start_at.date()).days
        if days_since < 0:
            return None
        return _combine_date_time(start_at.date() + timedelta(days=(days_since // 7) * 7), start_at)
    if task.recurrence == ScheduledTaskRecurrence.MONTHLY:
        try:
            candidate = _combine_date_time(date(now.year, now.month, start_at.day), start_at)
        except ValueError:
            return None
        return candidate
    if task.recurrence == ScheduledTaskRecurrence.YEARLY:
        try:
            candidate = _combine_date_time(date(now.year, start_at.month, start_at.day), start_at)
        except ValueError:
            return None
        return candidate
    return None


def _combine_date_time(day: date, source: datetime) -> datetime:
    return to_utc(datetime.combine(day, source.timetz()))


def _normalize_datetime(value: datetime) -> datetime:
    return to_utc(value)
