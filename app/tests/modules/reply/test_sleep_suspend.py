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
        # 收尾必须是一条真实回复：空轮次（无正文且无工具调用）现在会被判定为
        # 失败并留痕，用它当循环终止符会让本用例去断言一个与本意无关的状态。
        {"content": "我在", "tool_calls": []},
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


# ── @ 提及命中玩法关键词：跳过收集窗口 ─────────────────────────────


class _SleepSpy:
    """记录 asyncio.sleep 调用的替身（其余属性透传给真实 asyncio）。"""

    def __init__(self, real, calls) -> None:
        self._real = real
        self._calls = calls

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, seconds) -> None:
        self._calls.append(float(seconds))


def _fake_clock(start: float = 0.0, step: float = 0.25):
    """假单调时钟：每次读取前进 step 秒，让挂起循环无需真实等待。"""
    state = {"now": start - step}

    def _now() -> float:
        state["now"] += step
        return state["now"]

    return _now


def _register_keywords(monkeypatch, *keywords: str) -> None:
    from neobot_app.message import fast_reply_keywords
    from neobot_app.reply import orchestrator as orchestrator_module

    fast_reply_keywords.register_reply_trigger_keywords("minigame", keywords)
    slept: list[float] = []
    monkeypatch.setattr(orchestrator_module, "asyncio", _SleepSpy(asyncio, slept))
    monkeypatch.setattr(orchestrator_module, "monotonic_seconds", _fake_clock())
    return slept


@pytest.mark.asyncio
async def test_suspend_at_mention_keyword_ends_immediately(monkeypatch):
    """被@且正文命中玩法关键词：不进收集窗口，一轮就结束挂起。"""
    slept = _register_keywords(monkeypatch, "签到", "抽签")

    pipeline = _orchestrator(SleepService())
    pipeline._config = _config(suspend_seconds=3, at_delay=30)
    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(11, "签到", at_bot=True))

    new_entries, notification_text, wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert [entry.message.message_id for entry in new_entries] == [11]
    assert notification_text is None
    assert wake_prompt is None
    assert len(slept) == 1, "命中玩法关键词应立即结束挂起（只做首次轮询）"


@pytest.mark.asyncio
async def test_suspend_at_mention_without_keyword_keeps_window(monkeypatch):
    """回归：没命中关键词时仍然走收集窗口（多轮轮询后才结束）。"""
    slept = _register_keywords(monkeypatch)

    pipeline = _orchestrator(SleepService())
    pipeline._config = _config(suspend_seconds=3, at_delay=30)
    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(12, "hello", at_bot=True))

    new_entries, _notification_text, _wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert [entry.message.message_id for entry in new_entries] == [12]
    assert len(slept) > 1, "未命中关键词应继续等收集窗口"


@pytest.mark.asyncio
async def test_suspend_sleeping_at_mention_keyword_skips_window(monkeypatch):
    """睡眠中的挂起循环：@ 命中关键词时唤醒后立即结束，不等收集窗口。"""
    slept = _register_keywords(monkeypatch, "签到")

    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline = _orchestrator(sleep_service)
    pipeline._config = _config(suspend_seconds=3, at_delay=30)
    source = MessageQueue()
    snapshot = MessageQueue()
    source.push("42", _group_message(13, "帮我签到", at_bot=True))

    new_entries, notification_text, wake_prompt = await pipeline._suspend_group_chat(
        source, snapshot, "42"
    )

    assert [entry.message.message_id for entry in new_entries] == [13]
    assert notification_text is None
    assert wake_prompt == DEFAULT_WAKE_PROMPT
    assert not sleep_service.is_sleeping()
    assert len(slept) == 1

