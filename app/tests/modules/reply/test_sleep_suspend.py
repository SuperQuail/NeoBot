"""睡眠拦截测试:agent 群聊挂起循环在睡眠期间的忽略/唤醒行为。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.runtime.sleep_service import DEFAULT_WAKE_PROMPT, SleepService

BOT = 88888


def _config(*, suspend_seconds: int = 2, at_delay: float = 0.0):
    return SimpleNamespace(
        chat=SimpleNamespace(
            group_chat_suspend_wait_seconds=suspend_seconds,
            at_mention_reply_delay_seconds=at_delay,
        )
    )


class _FakeWilling:
    """最小意愿假件:真实 at 段识别 + 一律应回。"""

    def __init__(self, bot_account: int) -> None:
        self._bot = str(bot_account)

    def is_at_mentioned(self, message) -> bool:
        for segment in getattr(message, "message", None) or []:
            if getattr(segment, "type", None) != "at":
                continue
            if str(getattr(segment, "data", {}).get("qq", "")) == self._bot:
                return True
        return False

    def block_reason_for_message(self, **kwargs) -> str:
        return ""

    def evaluate(self, **kwargs):
        return SimpleNamespace(probability=1.0, should_reply=True, reasons=("fake",))


def _orchestrator(sleep_service: SleepService | None = None) -> ReplyOrchestrator:
    pipeline = object.__new__(ReplyOrchestrator)
    pipeline._sleep_service = sleep_service
    pipeline._willing_service = _FakeWilling(BOT)
    pipeline._logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    pipeline._config = _config()
    pipeline._notification_hub = None
    pipeline._drawing_manager = None
    pipeline._scheduled_task_manager = None
    pipeline._problem_solver_manager = None
    pipeline._reply_block_registry = None
    return pipeline


def _group_message(message_id: int, text: str, *, at_bot: bool = False) -> GroupMessage:
    segments: list[MessageSegment] = [
        MessageSegment(type="text", data={"text": text})
    ]
    if at_bot:
        segments.append(MessageSegment(type="at", data={"qq": str(BOT)}))
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(user_id=7, nickname="tester"),
        message=segments,
        raw_message=text,
    )


@pytest.mark.asyncio
async def test_suspend_during_sleep_ignores_plain_messages():
    """睡眠中挂起循环:普通消息被忽略,不结束挂起,不唤醒 Bot。"""
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline = _orchestrator(sleep_service)

    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(1, "hello"))

    new_entries, notification_text, wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert new_entries == []
    assert notification_text is None
    assert wake_prompt is None
    assert sleep_service.is_sleeping()


@pytest.mark.asyncio
async def test_suspend_during_sleep_at_mention_wakes():
    """睡眠中挂起循环:被@唤醒,返回新条目与唤醒提示词,睡眠结束。"""
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline = _orchestrator(sleep_service)

    source = MessageQueue()
    snapshot = MessageQueue()
    message = _group_message(2, "hi", at_bot=True)
    source.push("42", message)

    new_entries, notification_text, wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert len(new_entries) == 1
    assert new_entries[0].message.message_id == 2
    assert notification_text is None
    assert wake_prompt == DEFAULT_WAKE_PROMPT
    assert not sleep_service.is_sleeping()


@pytest.mark.asyncio
async def test_suspend_not_sleeping_plain_message_willing_hits():
    """未睡眠:普通消息按意愿判断结束挂起(回归,不含唤醒提示词)。"""
    pipeline = _orchestrator(SleepService())

    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(3, "hello"))

    new_entries, notification_text, wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert len(new_entries) == 1
    assert notification_text is None
    assert wake_prompt is None


@pytest.mark.asyncio
async def test_suspend_during_sleep_blocked_at_does_not_wake():
    """睡眠挂起中的被屏蔽 @ 不唤醒、不返回回复条目，仍更新快照。"""
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline = _orchestrator(sleep_service)
    pipeline._willing_service.block_reason_for_message = lambda **kw: "runtime_blacklisted"
    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(4, "blocked", at_bot=True))

    result = await pipeline._suspend_group_chat(source, snapshot, "42")

    assert result == ([], None, None)
    assert sleep_service.is_sleeping()
    assert pipeline._collect_new_entries(source, snapshot, "42") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [True, False])
async def test_wait_during_sleep_checks_at_block_reason(monkeypatch, blocked):
    """真实 agent wait 入口仅允许未被屏蔽的 @ 结束睡眠。"""
    from .test_orchestrator import (
        _ScriptedProvider,
        _make_decision,
        _make_orchestrator,
    )

    source = MessageQueue()
    sleep_service = SleepService()
    sleep_service.sleep(3600)

    class _WaitProvider(_ScriptedProvider):
        async def chat(self, messages, tools=None):
            if not self.calls:
                source.push("42", _group_message(6, "wake", at_bot=True))
            return await super().chat(messages, tools)

    provider = _WaitProvider([
        {"content": "", "tool_calls": [{
            "id": "sleep-wait", "type": "function",
            "function": {"name": "wait", "arguments": '{"seconds": 1}'},
        }]},
        {"content": "", "tool_calls": []},
    ])
    pipeline = _make_orchestrator(provider=provider, group_queue=source)
    pipeline._sleep_service = sleep_service
    pipeline._willing_service = _FakeWilling(BOT)
    pipeline._willing_service.block_reason_for_message = (
        lambda **kw: "runtime_blacklisted" if blocked else ""
    )

    async def no_suspend(*args):
        return [], None, None

    monkeypatch.setattr(pipeline, "_suspend_group_chat", no_suspend)

    try:
        event = pipeline.start_reply(
            message=_group_message(5, "start"), queue=source,
            queue_key="42", decision=_make_decision(),
        )
        assert event is not None
        await asyncio.wait_for(asyncio.gather(*pipeline._tasks), timeout=10)

        assert event.error is None
        assert len(provider.calls) >= 2
        tool_messages = [m for m in provider.calls[1][0] if m.get("role") == "tool"]
        assert any(("暂不处理" if blocked else "被@叫醒") in m["content"] for m in tool_messages)
        assert sleep_service.is_sleeping() is blocked
    finally:
        await pipeline.shutdown()
