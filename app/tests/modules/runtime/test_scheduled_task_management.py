"""定时任务管理投影（面板「定时任务」页的只读数据源）。

写操作统一走 reminder skill（见 skills/reminder_skill.py），这里只验证
面板需要的字段与「下次触发时间」的计算，避免面板另写一套统计。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import (
    ScheduledTaskRecord,
    ScheduledTaskRecurrence,
    ScheduledTaskState,
)
from neobot_app.runtime.scheduled_tasks import (
    ScheduledTaskConfig,
    ScheduledTaskManager,
    _next_occurrence_start,
)
from neobot_app.time_context import LOCAL_TIMEZONE, now_utc


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **kw) -> None:
        self.warnings.append(message)

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        pass

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


class _FakeScheduledTasksRepo:
    def __init__(self, records: list[ScheduledTaskRecord]) -> None:
        self.records = list(records)
        self.calls: list[dict] = []

    async def list(self, *, include_disabled=False, limit=50, offset=0):
        self.calls.append(
            {"include_disabled": include_disabled, "limit": limit, "offset": offset}
        )
        items = [
            record
            for record in self.records
            if include_disabled or record.state == ScheduledTaskState.ACTIVE
        ]
        return items[offset : offset + limit]

    async def get(self, task_uuid: str):
        for record in self.records:
            if record.task_uuid == task_uuid:
                return record
        return None


class _FakeUow:
    def __init__(self, repo: _FakeScheduledTasksRepo) -> None:
        self.scheduled_tasks = repo

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def commit(self) -> None:
        pass


def _uow_factory(repo: _FakeScheduledTasksRepo):
    def factory() -> _FakeUow:
        return _FakeUow(repo)

    return factory


def _record(
    task_uuid: str = "t-1",
    *,
    recurrence: ScheduledTaskRecurrence = ScheduledTaskRecurrence.DAILY,
    state: ScheduledTaskState = ScheduledTaskState.ACTIVE,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    metadata: dict | None = None,
) -> ScheduledTaskRecord:
    start = start_at or (now_utc() + timedelta(hours=1))
    return ScheduledTaskRecord(
        id=1,
        task_uuid=task_uuid,
        title="喝水提醒",
        detail="每小时提醒一次",
        recurrence=recurrence,
        start_at=start,
        end_at=end_at or (start + timedelta(minutes=10)),
        bindings=(ConversationRef(kind="group", id="888"),),
        metadata=metadata or {},
        state=state,
    )


def _manager(records: list[ScheduledTaskRecord]) -> tuple[ScheduledTaskManager, _FakeScheduledTasksRepo]:
    repo = _FakeScheduledTasksRepo(records)
    manager = ScheduledTaskManager(
        uow_factory=_uow_factory(repo),
        config=ScheduledTaskConfig(poll_interval_seconds=60),
        logger=_Logger(),
    )
    return manager, repo


async def test_list_managed_tasks_exposes_full_fields() -> None:
    """面板需要的字段必须齐全:UUID、窗口、绑定列表、通知策略、下次触发。"""
    manager, _ = _manager([_record(metadata={"one_shot_notification": False})])

    tasks = await manager.list_managed_tasks()

    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_id"] == "t-1"
    assert task["title"] == "喝水提醒"
    assert task["detail"] == "每小时提醒一次"
    assert task["recurrence"] == "daily"
    assert task["state"] == "active"
    assert task["enabled"] is True
    assert task["start_at"] and task["end_at"]
    assert task["start_at_local"].count("T") == 1
    assert task["next_run"]
    assert task["bindings"] == [{"kind": "group", "id": "888"}]
    assert task["one_shot_notification"] is False
    assert task["created_at"] and task["updated_at"]


async def test_list_managed_tasks_includes_disabled_by_default() -> None:
    """面板必须能看到并管理已停用任务,因此默认包含 disabled。"""
    manager, repo = _manager(
        [
            _record("t-active"),
            _record("t-disabled", state=ScheduledTaskState.DISABLED),
        ]
    )

    tasks = await manager.list_managed_tasks()

    assert {task["task_id"] for task in tasks} == {"t-active", "t-disabled"}
    disabled = next(task for task in tasks if task["task_id"] == "t-disabled")
    assert disabled["enabled"] is False
    # 停用任务没有下一次触发时间
    assert disabled["next_run"] == ""
    assert repo.calls[-1]["include_disabled"] is True


async def test_list_managed_tasks_honours_include_disabled_and_limit() -> None:
    manager, repo = _manager(
        [
            _record("t-active"),
            _record("t-disabled", state=ScheduledTaskState.DISABLED),
        ]
    )

    tasks = await manager.list_managed_tasks(include_disabled=False, limit=1)

    assert [task["task_id"] for task in tasks] == ["t-active"]
    assert repo.calls[-1] == {"include_disabled": False, "limit": 1, "offset": 0}


async def test_list_managed_tasks_without_storage_returns_empty() -> None:
    manager = ScheduledTaskManager(uow_factory=None, logger=_Logger())

    assert await manager.list_managed_tasks() == []


async def test_get_managed_task_reads_single_record() -> None:
    manager, _ = _manager([_record("t-1")])

    task = await manager.get_managed_task("t-1")
    missing = await manager.get_managed_task("nope")

    assert task is not None and task["task_id"] == "t-1"
    assert missing is None


async def test_next_occurrence_advances_daily_task_to_today() -> None:
    """已过期的每日任务,下次触发应落在今天的时间点而不是原始 start_at。"""
    anchor = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    task = _record(
        recurrence=ScheduledTaskRecurrence.DAILY,
        start_at=anchor,
        end_at=anchor + timedelta(minutes=10),
    )
    now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

    assert _next_occurrence_start(task, now) == datetime(
        2026, 3, 6, 9, 0, tzinfo=timezone.utc
    )


async def test_next_occurrence_keeps_current_window_and_clamps_month_end() -> None:
    """窗口内返回窗口起点;每月 31 号的任务在 2 月钳位到月末。"""
    anchor = datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    task = _record(
        recurrence=ScheduledTaskRecurrence.MONTHLY,
        start_at=anchor,
        end_at=anchor + timedelta(hours=1),
    )

    inside = _next_occurrence_start(task, datetime(2026, 2, 28, 8, 30, tzinfo=timezone.utc))
    assert inside == datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc)

    after = _next_occurrence_start(task, datetime(2026, 2, 28, 23, 0, tzinfo=timezone.utc))
    assert after == datetime(2026, 3, 31, 8, 0, tzinfo=timezone.utc)


async def test_next_occurrence_returns_none_for_elapsed_once_task() -> None:
    anchor = now_utc() - timedelta(hours=2)
    task = _record(
        recurrence=ScheduledTaskRecurrence.ONCE,
        start_at=anchor,
        end_at=anchor + timedelta(minutes=5),
    )

    assert _next_occurrence_start(task, now_utc()) is None


async def test_task_detail_local_time_matches_dashboard_input_format() -> None:
    """datetime-local 输入需要本地时区的 YYYY-MM-DDTHH:MM。"""
    start = datetime(2026, 5, 1, 9, 0, tzinfo=LOCAL_TIMEZONE)
    manager, _ = _manager([_record(start_at=start.astimezone(timezone.utc))])

    task = (await manager.list_managed_tasks())[0]

    assert task["start_at_local"].startswith("2026-05-01T09:00")
