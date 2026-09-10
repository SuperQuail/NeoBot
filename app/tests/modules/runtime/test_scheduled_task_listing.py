"""面板「后台任务」里的定时任务列表必须有数据。

dashboard/api.py 的 /api/tasks 用 getattr(manager, "list_tasks", None) 探测接口，
而 ScheduledTaskManager 之前没有该方法 → 面板里的定时任务恒为空且不报错。
"""

from __future__ import annotations

from datetime import timedelta

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import (
    ScheduledTaskRecurrence,
    ScheduledTaskRecord,
    ScheduledTaskState,
)
from neobot_app.runtime.scheduled_tasks import ScheduledTaskConfig, ScheduledTaskManager
from neobot_app.time_context import now_utc


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


def _record(task_uuid: str = "t-1") -> ScheduledTaskRecord:
    start = now_utc() + timedelta(hours=1)
    return ScheduledTaskRecord(
        id=1,
        task_uuid=task_uuid,
        title="喝水提醒",
        detail="每小时提醒一次",
        recurrence=ScheduledTaskRecurrence.DAILY,
        start_at=start,
        end_at=start + timedelta(minutes=10),
        bindings=(ConversationRef(kind="group", id="888"),),
        state=ScheduledTaskState.ACTIVE,
    )


def _manager(records: list[ScheduledTaskRecord] | None = None) -> ScheduledTaskManager:
    logger = _Logger()
    manager = ScheduledTaskManager(
        uow_factory=object(),  # 只用于绕过 None 判定
        config=ScheduledTaskConfig(poll_interval_seconds=60),
        logger=logger,
    )
    manager._logger = logger

    async def _list() -> list[ScheduledTaskRecord]:
        return list(records or [])

    manager._list_active_tasks = _list  # type: ignore[assignment]
    return manager


async def test_list_tasks_returns_panel_fields() -> None:
    manager = _manager([_record()])

    items = await manager.list_tasks()

    assert len(items) == 1
    item = items[0]
    assert item["task_id"] == "t-1"
    assert item["description"] == "每小时提醒一次"
    assert item["status"] == "active"
    assert item["recurrence"] == "daily"
    # 面板显示的时间字段
    assert item["next_run"] and item["trigger_time"]
    assert item["bindings"] == 1


async def test_list_tasks_without_storage_returns_empty() -> None:
    manager = ScheduledTaskManager(uow_factory=None, logger=_Logger())

    assert await manager.list_tasks() == []


async def test_list_tasks_swallows_read_errors() -> None:
    """读取失败只记日志并返回空列表，不能让面板 500。"""
    manager = _manager()

    async def _boom() -> list[ScheduledTaskRecord]:
        raise RuntimeError("db down")

    manager._list_active_tasks = _boom  # type: ignore[assignment]

    assert await manager.list_tasks() == []
    assert manager._logger.warnings


async def test_list_tasks_respects_limit() -> None:
    manager = _manager([_record(f"t-{i}") for i in range(5)])

    assert len(await manager.list_tasks(limit=2)) == 2
