from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neobot_app.runtime import scheduled_tasks as task_module
from neobot_app.runtime.scheduled_tasks import ScheduledTaskManager
from neobot_contracts.ports.logging import NullLogger


class Recorder(NullLogger):
    def __init__(self):
        self.records = []

    def warning(self, message, **fields):
        self.records.append(("WARNING", message, fields))

    def info(self, message, **fields):
        self.records.append(("INFO", message, fields))


@pytest.mark.asyncio
async def test_poll_failure_is_deduplicated_and_reports_recovery(monkeypatch):
    recorder = Recorder()
    manager = ScheduledTaskManager(logger=recorder)
    clock = {"now": 100.0}
    monkeypatch.setattr(task_module, "monotonic_seconds", lambda: clock["now"])
    manager.scan_due_tasks = AsyncMock(
        side_effect=[
            RuntimeError("database busy"),
            RuntimeError("database busy"),
            RuntimeError("database busy"),
            None,
        ]
    )
    ticks = 0

    async def tick(_):
        nonlocal ticks
        ticks += 1
        clock["now"] += 150.0
        if ticks == 4:
            manager._stopping.set()

    monkeypatch.setattr(task_module.asyncio, "sleep", tick)
    await manager._run_loop()

    assert manager.scan_due_tasks.await_count == 4
    assert [(level, text) for level, text, _ in recorder.records] == [
        ("WARNING", "定时任务扫描失败"),
        ("WARNING", "定时任务扫描失败"),
        ("INFO", "定时任务扫描已恢复"),
    ]
    assert recorder.records[1][2]["suppressed_count"] == 1
    assert manager._failure_logs == {}


def test_changed_poll_error_is_reported_immediately_and_storage_is_bounded(monkeypatch):
    recorder = Recorder()
    manager = ScheduledTaskManager(logger=recorder)
    monkeypatch.setattr(task_module, "monotonic_seconds", lambda: 100.0)
    manager._log_poll_failure("收尾", ValueError("bad window"), task_id="task-1")
    manager._log_poll_failure("收尾", RuntimeError("database busy"), task_id="task-1")
    assert len(recorder.records) == 2
    assert recorder.records[1][2]["error_type"] == "RuntimeError"

    for number in range(200):
        manager._log_poll_failure("收尾", RuntimeError("database busy"), task_id=str(number))
    assert len(manager._failure_logs) == task_module._MAX_FAILURE_LOG_STATES
