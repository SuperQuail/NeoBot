from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from loguru import logger

from neobot_adapter.onebot.adapter import OneBotAdapter
from neobot_adapter.onebot.receiver import core as core_module
from neobot_adapter.onebot.receiver.core import AdapterCore
from neobot_contracts.ports.logging import NullLogger


@pytest.mark.asyncio
async def test_heartbeat_reports_timeout_once_until_recovery(monkeypatch):
    core = AdapterCore()
    core._heartbeat_interval = 1.0
    core._last_heartbeat_time = 1.0
    clock = {"now": 1.0, "ticks": 0}
    records = []
    sink = logger.add(lambda message: records.append(message.record), format="{message}")
    monkeypatch.setattr(core_module, "time", SimpleNamespace(monotonic=lambda: clock["now"]))

    async def tick(_):
        clock["ticks"] += 1
        clock["now"] = [5.0, 6.0, 7.0, 11.0, 12.0][clock["ticks"] - 1]
        if clock["ticks"] == 3:
            await core._handle_meta_event(
                {
                    "post_type": "meta_event",
                    "meta_event_type": "heartbeat",
                    "interval": 1000,
                }
            )
        if clock["ticks"] == 5:
            core._stop_event.set()

    monkeypatch.setattr(core_module.asyncio, "sleep", tick)
    try:
        await core._check_heartbeat()
    finally:
        logger.remove(sink)

    messages = [record["message"] for record in records]
    assert messages.count("OneBot 心跳超时") == 2
    assert messages.count("OneBot 心跳已恢复") == 1
    assert [record["level"].name for record in records] == ["WARNING", "INFO", "WARNING"]


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_response", [False, True])
async def test_api_request_logs_metadata_without_message_body(wait_response):
    core = AdapterCore()
    records = []
    sink = logger.add(lambda message: records.append(message.record), format="{message}")
    websocket = AsyncMock()

    async def send(payload):
        request = json.loads(payload)
        assert not records
        if wait_response:
            await core._fulfill_echo(websocket, request["echo"], {"status": "ok"})

    websocket.send.side_effect = send
    try:
        result = await core._call_action(
            websocket,
            "send_group_msg",
            {"group_id": 42, "message": "private-message-content"},
            wait_response=wait_response,
        )
    finally:
        logger.remove(sink)

    assert result["status"] == "ok"
    sent = [record for record in records if record["extra"].get("event") == "onebot.api.sent"]
    assert len(sent) == 1
    assert sent[0]["level"].name == "DEBUG"
    assert sent[0]["extra"]["action"] == "send_group_msg"
    assert sent[0]["extra"]["wait_response"] is wait_response
    assert "private-message-content" not in str(records)


@pytest.mark.asyncio
async def test_handler_failure_reports_identity_without_stopping_later_handlers():
    class Recorder(NullLogger):
        def __init__(self):
            self.failures = []

        def exception(self, message, **fields):
            self.failures.append((message, fields))

    recorder = Recorder()
    adapter = OneBotAdapter(logger=recorder)
    delivered = []

    @adapter.on.message.group
    async def broken(event):
        raise ValueError("invalid handler state")

    @adapter.on.message.group
    async def healthy(event):
        delivered.append(event["message_id"])

    await adapter._dispatcher.publish(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 42,
            "message_id": 8,
            "raw_message": "private-message-content",
        }
    )

    assert delivered == [8]
    assert len(recorder.failures) == 1
    message, fields = recorder.failures[0]
    assert message == "事件处理失败"
    assert fields["handler"].endswith("broken")
    assert fields["message_id"] == 8
    assert fields["group_id"] == 42
    assert fields["error"] == "invalid handler state"
    assert "raw_message" not in fields
