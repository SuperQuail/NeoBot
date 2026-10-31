"""正常通知只记录一次交付，丢弃时保留被影响任务的来源。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_contracts.ports.logging import NullLogger
from neobot_app.runtime.notifications import BackgroundNotificationHub


class RecordingLogger(NullLogger):
    def __init__(self):
        self.records = []

    def debug(self, message, **fields):
        self.records.append(("debug", message, fields))

    def info(self, message, **fields):
        self.records.append(("info", message, fields))

    def warning(self, message, **fields):
        self.records.append(("warning", message, fields))


@pytest.mark.asyncio
async def test_started_notification_has_one_delivery_record():
    logger = RecordingLogger()
    reply = SimpleNamespace(event_id="reply-1")
    orchestrator = SimpleNamespace(
        is_pipeline_key_active=lambda key: False,
        start_background_reply=lambda **kwargs: reply,
    )
    hub = BackgroundNotificationHub(orchestrator=orchestrator, logger=logger)

    started = await hub.publish(
        source="drawing",
        kind="private",
        conversation_id="42",
        content="完成",
        metadata={"task_id": "task-1"},
    )

    assert started
    assert len(logger.records) == 1
    level, _, fields = logger.records[0]
    assert level == "debug"
    assert fields["event"] == "notification.consumed"
    assert fields["event_id"] == "reply-1"
    assert fields["task_id"] == "task-1"
    assert fields["chat_flow_id"] == "private:42"


@pytest.mark.asyncio
async def test_notification_drop_identifies_lost_task_and_keeps_new_notification():
    logger = RecordingLogger()
    hub = BackgroundNotificationHub(logger=logger)
    hub._queue_max_size = 1
    for task_id in ["old", "new"]:
        await hub.publish(
            source="drawing",
            kind="private",
            conversation_id="42",
            content=task_id,
            metadata={"task_id": task_id},
        )

    alerts = [fields for level, _, fields in logger.records if level == "warning"]
    assert len(alerts) == 1
    assert alerts[0]["event"] == "notification.dropped"
    assert alerts[0]["chat_flow_id"] == "private:42"
    assert alerts[0]["dropped_source"] == "drawing"
    assert alerts[0]["dropped_task_id"] == "old"
    notification = await hub.poll("private:42")
    assert notification is not None
    assert notification.metadata["task_id"] == "new"
