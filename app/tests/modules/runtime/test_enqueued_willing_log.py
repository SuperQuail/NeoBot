"""消息入队日志：一条 INFO 带出意愿概率/是否回复/原因。

意愿判定的分散 DEBUG 记录收敛到 message.enqueued；接收摘要降为 DEBUG，
同一消息在 INFO 级别只留入队这一条。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_contracts.ports.logging import NullLogger
from neobot_app.config.schemas.bot import Bot, BotConfig, Chat
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.runtime.sleep_service import SleepService

from .test_event_pipeline import _pipeline_with_queue


class _RecordingLogger(NullLogger):
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def debug(self, message: str, **fields) -> None:
        self.records.append(("debug", message, fields))

    def info(self, message: str, **fields) -> None:
        self.records.append(("info", message, fields))

    def warning(self, message: str, **fields) -> None:
        self.records.append(("warning", message, fields))


def _enqueued(logger: _RecordingLogger) -> list[dict]:
    return [
        fields for level, _, fields in logger.records if level == "info" and fields.get("event") == "message.enqueued"
    ]


def _config() -> BotConfig:
    return BotConfig(
        bot=Bot(account=0),
        chat=Chat(
            private_chat_dynamic_warmup=False,
            private_chat_reply_delay_seconds=0.0,
            at_mention_reply_delay_seconds=0.0,
        ),
    )


def _group_event(message_id: int = 1, text: str = "hello") -> dict:
    return {
        "post_type": "message",
        "message_type": "group",
        "message_id": message_id,
        "user_id": 7,
        "group_id": 42,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _private_event(message_id: int = 1, text: str = "hello") -> dict:
    return {
        "post_type": "message",
        "message_type": "private",
        "message_id": message_id,
        "user_id": 8,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _willing(*, at_mentioned: bool = False, block_reason: str = "", decision=None):
    return SimpleNamespace(
        is_at_mentioned=lambda _m: at_mentioned,
        block_reason_for_message=lambda **_kw: block_reason,
        evaluate=lambda **_kw: decision,
    )


async def test_group_enqueued_log_carries_willingness_fields() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger
    pipeline._willing_service = _willing(
        decision=SimpleNamespace(probability=0.42, should_reply=False, reasons=("最终概率=0.420",))
    )

    await pipeline.handle_group_message_event(_group_event(text="x" * 120))

    logs = _enqueued(logger)
    assert len(logs) == 1
    fields = logs[0]
    assert fields["queue_key"] == "42"
    assert fields["chat_flow_id"] == "group:42"
    assert fields["conversation_kind"] == "group"
    assert fields["conversation_id"] == "42"
    assert fields["message_id"] == 1
    assert fields["sender_id"] == "7"
    assert fields["preview"] == "x" * 80
    assert fields["willingness"] == {
        "probability": 0.42,
        "should_reply": False,
        "reasons": ["最终概率=0.420"],
    }


async def test_private_enqueued_log_is_direct_reply_with_delay() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger
    pipeline._reply_orchestrator = SimpleNamespace(start_reply=lambda **_kw: object())

    await pipeline.handle_private_message_event(_private_event())

    logs = _enqueued(logger)
    assert len(logs) == 1
    fields = logs[0]
    assert fields["chat_flow_id"] == "private:8"
    assert fields["conversation_kind"] == "private"
    assert fields["conversation_id"] == "8"
    assert fields["sender_id"] == "8"
    assert fields["delay_seconds"] == 0.0
    assert fields["willingness"] == {
        "probability": 1.0,
        "should_reply": True,
        "reasons": ["私聊直接回复（跳过意愿管理器）"],
    }


async def test_at_mention_enqueued_log_is_direct_trigger() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger
    pipeline._reply_orchestrator = SimpleNamespace(start_reply=lambda **_kw: object())
    pipeline._willing_service = _willing(at_mentioned=True)

    await pipeline.handle_group_message_event(_group_event(text="hi"))

    logs = _enqueued(logger)
    assert len(logs) == 1
    assert logs[0]["willingness"] == {
        "probability": 1.0,
        "should_reply": True,
        "reasons": ["被@提及，直接触发"],
    }
    # 意愿判定不再单独打 debug reply.decided；入队日志是唯一记录
    assert [fields for _, _, fields in logger.records if fields.get("event") == "reply.decided"] == []


async def test_blocked_enqueued_log_explains_reason() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger
    pipeline._willing_service = _willing(at_mentioned=True, block_reason="group_blacklisted")

    await pipeline.handle_group_message_event(_group_event(text="hi"))

    logs = _enqueued(logger)
    assert len(logs) == 1
    assert logs[0]["willingness"] == {
        "probability": 0.0,
        "should_reply": False,
        "reasons": ["已屏蔽: group_blacklisted"],
    }


async def test_sleeping_enqueued_log_explains_no_reply() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    pipeline._willing_service = _willing()

    await pipeline.handle_group_message_event(_group_event())

    logs = _enqueued(logger)
    assert len(logs) == 1
    assert logs[0]["willingness"] == {
        "probability": 0.0,
        "should_reply": False,
        "reasons": ["睡眠中，不触发回复"],
    }
    assert sleep_service.is_sleeping()


async def test_missing_willing_service_still_logs_enqueued_with_reason() -> None:
    pipeline = _pipeline_with_queue(config=_config())
    logger = _RecordingLogger()
    pipeline._logger = logger

    await pipeline.handle_group_message_event(_group_event())

    logs = _enqueued(logger)
    assert len(logs) == 1
    assert logs[0]["willingness"] == {
        "probability": 0.0,
        "should_reply": False,
        "reasons": ["意愿服务未启用，不触发回复"],
    }


async def test_received_log_is_debug_not_a_second_info() -> None:
    logger = _RecordingLogger()
    pipeline = InboundPipeline(adapter=SimpleNamespace(), logger=logger)
    message = IncomingMessage(
        event_id="e1",
        conversation=ConversationRef(kind="group", id="42"),
        sender_id="7",
        sender_name="tester",
        text="hello",
        occurred_at=datetime.now(),
    )

    await pipeline.handle(message)

    assert [(level, fields.get("event")) for level, _, fields in logger.records] == [("debug", "message.received")]
