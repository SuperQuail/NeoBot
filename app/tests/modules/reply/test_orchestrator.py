"""ReplyOrchestrator 测试：agent 模式 wait 工具 previous_entries 初始化、管线去重、shutdown、队列差集逻辑。"""

from __future__ import annotations

import asyncio
import json

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import (
    GroupMessage,
    MessageSegment,
    MessageTypeEnum,
    PrivateMessage,
)
from neobot_app.message.queue import MessageQueue, QueueEntry, QueueEntryType
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.willing.models import WillingDecision


class _FakeChat:
    """除显式字段外，所有配置属性默认返回 None（触发源模块的默认分支）。"""

    reply_mode = "agent"

    def __getattr__(self, name: str):
        return None


class _FakeBot:
    nick_name = "Bot"


class _FakeConfig:
    chat = _FakeChat()
    bot = _FakeBot()


class _FakePromptBuilder:
    async def build_friend_chat_prompt(self, **kwargs):
        return "私聊提示词"

    async def build_group_chat_prompt(self, **kwargs):
        return "群聊提示词"


class _HangingProvider:
    """chat 永远挂起，用于保持管线活跃。"""

    async def chat(self, messages, tools=None):
        await asyncio.Event().wait()

    async def close(self):
        pass


class _ScriptedProvider:
    """按脚本依次返回响应，用于最小 agent 循环。"""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list, object]] = []

    async def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        return self._responses.pop(0)

    async def close(self):
        pass


class _FakeAdapter:
    async def send(self, conversation_ref, payload):
        return {"status": "ok", "message_id": 2001}

    async def call_api(self, action, params):
        return {"status": "ok"}


def _make_private_message(message_id: int = 1, text: str = "你好") -> PrivateMessage:
    return PrivateMessage(
        message_type=MessageTypeEnum.private,
        message_id=message_id,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )


def _make_group_message(message_id: int = 1) -> GroupMessage:
    return GroupMessage(
        message_type=MessageTypeEnum.group,
        message_id=message_id,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": "群消息"})],
        raw_message="群消息",
        group_id=888888,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )


def _make_decision() -> WillingDecision:
    return WillingDecision(
        manager_name="test",
        probability=1.0,
        should_reply=True,
        reasons=("测试触发",),
    )


def _make_orchestrator(
    *,
    provider=None,
    prompt_builder=None,
    config=None,
    group_queue=None,
    friend_queue=None,
) -> ReplyOrchestrator:
    return ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=prompt_builder or _FakePromptBuilder(),
        provider=provider,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        config=config or _FakeConfig(),
        logger=None,
    )


# ── 管线去重（并发用例）──────────────────────────────────────────


async def test_start_reply_same_pipeline_key_concurrent_deduplicates():
    """同一 queue_key 并发调用两次 start_reply，必须只创建一条管线，第二次返回 None。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    decision = _make_decision()

    async def _start():
        return orch.start_reply(
            message=_make_private_message(),
            queue=queue,
            queue_key="123456",
            decision=decision,
        )

    results = await asyncio.gather(_start(), _start())

    assert [r for r in results if r is not None] == [results[0]]
    assert len(orch._active_pipelines) == 1
    assert orch.is_pipeline_active("private", "123456") is True
    await orch.shutdown()
    assert not orch._active_pipelines


async def test_start_reply_different_pipeline_keys_both_allowed():
    """不同 queue_key（私聊 vs 群聊）并发调用不得互相阻塞，两条管线都创建。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    friend_queue = MessageQueue()
    group_queue = MessageQueue()
    orch._group_queue = group_queue
    orch._friend_queue = friend_queue
    decision = _make_decision()

    first = orch.start_reply(
        message=_make_private_message(),
        queue=friend_queue,
        queue_key="123456",
        decision=decision,
    )
    second = orch.start_reply(
        message=_make_group_message(),
        queue=group_queue,
        queue_key="888888",
        decision=decision,
    )

    assert first is not None
    assert second is not None
    assert len(orch._active_pipelines) == 2
    await orch.shutdown()


# ── shutdown 取消任务 ────────────────────────────────────────────


async def test_shutdown_cancels_active_pipeline():
    """shutdown 必须取消所有运行中的管线任务并清空注册表，事件被标记 cancelled。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    await asyncio.sleep(0.05)

    await orch.shutdown()

    assert not orch._active_pipelines
    assert not orch._tasks
    assert event.error == "cancelled"


async def test_shutdown_without_active_tasks_is_noop():
    """无活跃任务时 shutdown 必须正常返回且不抛异常。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    await orch.shutdown()
    assert not orch._active_pipelines
    assert not orch._tasks


# ── agent 模式 wait 工具 previous_entries 初始化 ─────────────────


async def test_wait_tool_agent_loop_previous_entries_initialized(monkeypatch):
    """agent 模式首次调用 wait 工具时 previous_entries 已初始化，不得 UnboundLocalError，工具结果注入消息列表。"""
    provider = _ScriptedProvider([
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "wait", "arguments": json.dumps({"seconds": 1})},
                }
            ],
        },
        {"content": "收到", "tool_calls": []},
    ])
    orch = _make_orchestrator(provider=provider)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    for _ in range(200):
        if not orch._active_pipelines:
            break
        await asyncio.sleep(0.1)

    assert provider.calls, "provider 必须被调用"
    tool_messages = [
        m for m in provider.calls[1][0] if m.get("role") == "tool"
    ]
    assert any("没有收到新消息" in m["content"] for m in tool_messages)
    assert event.generated_text == "收到"
    assert event.error is None
    await orch.shutdown()


@pytest.mark.xfail(
    reason=(
        "BUG-0001 状态机缺 GENERATING->COMPLETED：私聊回复管线结束后事件停留在 "
        "GENERATING 且 completed_at 为 None，orchestrator.py:1623-1627 的 "
        "except RuntimeError 吞掉了非法转换异常"
    ),
    strict=False,
)
async def test_private_pipeline_event_reaches_completed_state(monkeypatch):
    """私聊回复管线结束后事件必须进入 COMPLETED 终态并写入 completed_at。"""
    provider = _ScriptedProvider([{"content": "你好", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    for _ in range(200):
        if not orch._active_pipelines:
            break
        await asyncio.sleep(0.1)

    assert event.state.name == "COMPLETED"
    assert event.completed_at is not None
    await orch.shutdown()


# ── _collect_new_entries 队列差集逻辑 ────────────────────────────


async def test_collect_new_entries_returns_only_new_and_updates_snapshot():
    """_collect_new_entries 只返回快照之后的新消息，且更新快照后再次调用返回空。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    source.push(key, _make_private_message(message_id=1, text="第一条"))
    snapshot = source.clone(key)
    source.push(key, _make_private_message(message_id=2, text="第二条"))

    first = orch._collect_new_entries(source, snapshot, key)
    second = orch._collect_new_entries(source, snapshot, key)

    assert [e.message.message_id for e in first] == [2]
    assert second == []


async def test_collect_new_entries_deduplicates_by_fingerprint():
    """相同 message_id 的消息重复推入源队列时，指纹去重后不得再次作为新条目返回。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    snapshot = MessageQueue()
    source.push(key, _make_private_message(message_id=1, text="第一条"))
    snapshot.append_entries(key, source.entries(key))

    source.push(key, _make_private_message(message_id=1, text="重复的旧消息"))
    new = orch._collect_new_entries(source, snapshot, key)

    assert new == []


async def test_consume_ai_reply_blocked_entries_filters_blocked():
    """reply_block_registry.consume_message 命中时必须过滤被插件拦截的消息条目。"""
    registry = type("BlockRegistry", (), {
        "consume_message": lambda self, m: m.message_id == 2,
    })()
    orch = _make_orchestrator()
    orch._reply_block_registry = registry
    entries = [
        QueueEntry(kind=QueueEntryType.MESSAGE, message=_make_private_message(message_id=1, text="a")),
        QueueEntry(kind=QueueEntryType.MESSAGE, message=_make_private_message(message_id=2, text="b")),
        QueueEntry(kind=QueueEntryType.MESSAGE, message=_make_private_message(message_id=3, text="c")),
    ]

    kept = orch._consume_ai_reply_blocked_entries(entries)

    assert [e.message.message_id for e in kept] == [1, 3]


async def test_consume_ai_reply_blocked_entries_without_registry_keeps_all():
    """未配置 reply_block_registry 时，_consume_ai_reply_blocked_entries 必须原样返回条目。"""
    orch = _make_orchestrator()
    entries = [
        QueueEntry(kind=QueueEntryType.MESSAGE, message=_make_private_message(message_id=1, text="a")),
    ]

    kept = orch._consume_ai_reply_blocked_entries(entries)

    assert kept == entries


# ── start_background_reply ───────────────────────────────────────


async def test_start_background_reply_creates_and_deduplicates_pipeline():
    """后台回复首次创建管线，同 key 重复调用返回 None；kind 为空时必须拒绝。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    orch._group_queue = MessageQueue()

    first = orch.start_background_reply(
        kind="group", conversation_id="123456", content="绘图完成",
    )
    second = orch.start_background_reply(
        kind="group", conversation_id="123456", content="绘图完成",
    )
    invalid = orch.start_background_reply(kind="", conversation_id="", content="x")

    assert first is not None
    assert second is None
    assert invalid is None
    assert orch.is_pipeline_active("group", "123456") is True
    await orch.shutdown()


# ── 静态纯逻辑 ───────────────────────────────────────────────────


def test_build_conversation_ref_detects_kind():
    """GroupMessage 与 message_type='group' 的合成消息识别为群聊，PrivateMessage 识别为私聊。"""
    assert ReplyOrchestrator._build_conversation_ref(_make_group_message(), "g1").kind == "group"
    assert ReplyOrchestrator._build_conversation_ref(_make_private_message(), "p1").kind == "private"

    synthetic = type("Synthetic", (), {"message_type": "group"})()
    assert ReplyOrchestrator._build_conversation_ref(synthetic, "g2").kind == "group"


def test_api_succeeded_judges_status():
    """_api_succeeded：None 视为失败，status=='ok' 视为成功，其余 status 视为失败，非 dict 视为成功。"""
    assert ReplyOrchestrator._api_succeeded(None) is False
    assert ReplyOrchestrator._api_succeeded({"status": "ok"}) is True
    assert ReplyOrchestrator._api_succeeded({"status": "failed", "message": "err"}) is False
    assert ReplyOrchestrator._api_succeeded({"message_id": 1}) is True
    assert ReplyOrchestrator._api_succeeded("raw string") is True


def test_estimate_tokens_scales_with_message_length():
    """_estimate_tokens 必须随消息体字符数增长（约 1 字符 ≈ 1.33 token）。"""
    short = ReplyOrchestrator._estimate_tokens([{"role": "user", "content": "短"}])
    long_ = ReplyOrchestrator._estimate_tokens([{"role": "user", "content": "长" * 300}])
    assert long_ > short
    assert long_ >= 300
