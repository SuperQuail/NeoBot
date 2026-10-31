"""回复日志按用户可见结果区分正常终止与真实故障。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import NullLogger
from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.flow_registry import ChatFlowRegistry
from neobot_app.reply.orchestrator_parts.modes import ModesMixin


class RecordingLogger(NullLogger):
    def __init__(self):
        self.records = []

    def debug(self, message, **fields):
        self.records.append(("debug", message, fields))

    def info(self, message, **fields):
        self.records.append(("info", message, fields))

    def warning(self, message, **fields):
        self.records.append(("warning", message, fields))

    def error(self, message, **fields):
        self.records.append(("error", message, fields))


class ReplyHarness(ModesMixin):
    def __init__(self):
        self._logger = RecordingLogger()
        self._adapter = SimpleNamespace()
        self._set_flow_active = lambda *args: None
        self.debug_events = []
        self._record_debug = lambda stage, event, **fields: self.debug_events.append((stage, fields))
        self._emit_runtime_event = AsyncMock(return_value=SimpleNamespace(consumed=False))
        self._run_agent_mode = AsyncMock()
        self._handle_runtime_failure = AsyncMock()


def make_event(**kwargs):
    return ReplyEvent(mode="agent", conversation_ref=ConversationRef("private", "42"), **kwargs)


def test_delivered_normal_cancel_is_not_an_alert_and_preserves_debug_reason():
    harness = ReplyHarness()
    event = make_event(
        state=ReplyState.CANCELLED,
        send_response={"message_id": 1},
        error="agent 主动取消回复",
    )

    assert harness._normalize_delivered_terminal(event, queue_key="42")

    assert event.state is ReplyState.COMPLETED
    assert event.error is None
    assert harness._logger.records == []
    assert harness.debug_events[0][1]["original_error"] == "agent 主动取消回复"


def test_delivered_failure_remains_visible_with_original_reason():
    harness = ReplyHarness()
    event = make_event(
        state=ReplyState.FAILED,
        send_response={"message_id": 1},
        error="model response truncated",
    )

    harness._normalize_delivered_terminal(event, queue_key="42")

    assert event.state is ReplyState.COMPLETED
    level, _, fields = harness._logger.records[0]
    assert level == "warning"
    assert fields["event"] == "reply.post_delivery_failed"
    assert fields["chat_flow_id"] == "private:42"
    assert fields["error"] == "model response truncated"


@pytest.mark.asyncio
async def test_post_delivery_exception_retains_diagnostics_without_losing_delivery():
    harness = ReplyHarness()
    harness._run_agent_mode.side_effect = ValueError("follow-up failed")
    event = make_event(state=ReplyState.GENERATING, send_response={"message_id": 1})

    await harness._run(event, SimpleNamespace(), "42")

    assert event.state is ReplyState.COMPLETED
    assert event.error is None
    assert len(harness._logger.records) == 1
    level, _, fields = harness._logger.records[0]
    assert level == "warning"
    assert fields["event"] == "reply.post_delivery_failed"
    assert fields["error_type"] == "ValueError"
    assert fields["error"] == "follow-up failed"
    assert fields["exc_info"] is True


@pytest.mark.asyncio
async def test_shutdown_cancellation_still_propagates_without_warning():
    harness = ReplyHarness()
    harness._run_agent_mode.side_effect = asyncio.CancelledError()
    event = make_event(state=ReplyState.GENERATING)

    with pytest.raises(asyncio.CancelledError):
        await harness._run(event, SimpleNamespace(), "42")

    assert event.state is ReplyState.CANCELLED
    assert not any(level in {"warning", "error"} for level, _, _ in harness._logger.records)


@pytest.mark.asyncio
async def test_unavailable_provider_has_one_failure_record():
    harness = ReplyHarness()
    error = RuntimeError("未配置 chat provider，无法生成回复")
    harness._run_agent_mode.side_effect = error
    helper = DebugHelper(logger=harness._logger)

    async def handle_runtime_failure(event, exc):
        await helper.handle_runtime_failure(event, exc, provider_error_message="", send_with_timeout=None)

    harness._handle_runtime_failure = handle_runtime_failure
    event = make_event(state=ReplyState.GENERATING)

    await harness._run(event, SimpleNamespace(), "42")

    assert event.state is ReplyState.FAILED
    failures = [fields for level, _, fields in harness._logger.records if level == "error"]
    assert len(failures) == 1
    assert failures[0]["event"] == "reply.failed"
    assert failures[0]["event_id"] == event.event_id
    assert failures[0]["error_type"] == "RuntimeError"


def test_unrenderable_flow_content_keeps_reply_alive_and_reports_missing_snapshot():
    class Unrenderable:
        def __str__(self):
            raise ValueError("cannot render content")

    logger = RecordingLogger()
    registry = ChatFlowRegistry(logger=logger)

    registry.record_request("private:42", messages=[{"role": "user", "content": Unrenderable()}])

    assert len(logger.records) == 1
    level, _, fields = logger.records[0]
    assert level == "warning"
    assert fields["chat_flow_id"] == "private:42"
    assert fields["error_type"] == "ValueError"
    assert fields["error"] == "cannot render content"
