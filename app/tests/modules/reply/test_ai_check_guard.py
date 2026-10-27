"""An AI-review turn cannot become a sent reply without a structured decision."""

from __future__ import annotations

import asyncio
import json
import tomllib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.store import TEMPLATES_DIR
from neobot_app.reply.event import ReplyState
from neobot_app.reply.tools import ReplyToolExecutor

from .test_orchestrator import (
    _FakeBot,
    _FakeChat,
    _ScriptedProvider,
    _make_decision,
    _make_group_message,
    _make_orchestrator,
    _make_private_message,
)


@pytest.mark.parametrize("section", ["group_chat", "friend_chat"])
def test_default_prompts_require_a_real_cancel_tool_call(section):
    prompts = tomllib.loads((TEMPLATES_DIR / "prompts.toml").read_text(encoding="utf-8"))
    text = prompts[section]["template"]
    assert "取消本轮回复必须直接调用 cancel 工具" in text
    assert "讨论或引用这个词不等于调用工具" in text
    assert "所有对外发言都必须通过工具调用" in text
    assert "没有调用发送工具就直接输出的正文不会被发送" in text


def test_send_reply_definition_declares_the_only_outlet():
    executor = ReplyToolExecutor(send_reply_handler=AsyncMock(return_value=True))
    definition = next(
        item
        for item in executor.definitions()
        if item["function"]["name"] == "send_reply"
    )

    assert "唯一出口" in definition["function"]["description"]


def tool_response(name, args):
    return {"content": "", "tool_calls": [{
        "id": "decision", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}


async def run_script(monkeypatch, responses, *, full_check=True, kind="group", extras=None):
    chat = _FakeChat()
    chat.ai_reply_check = full_check
    chat.ai_reply_check_lightweight = not full_check
    chat.group_chat_reply_lifespan = 0
    chat.sentence_cooldown_seconds = 0
    chat.private_chat_sentence_cooldown_seconds = 0
    provider = _ScriptedProvider(responses)
    orch = _make_orchestrator(provider=provider, config=SimpleNamespace(chat=chat, bot=_FakeBot()))
    sent = AsyncMock(return_value={"message_id": 1})
    monkeypatch.setattr(orch._adapter, "send", sent)
    # No real storage/network/model; the sender and agent loop remain real.
    monkeypatch.setattr(orch._sender, "persist_self_sent_message", AsyncMock())
    monkeypatch.setattr(orch, "_suspend_private_chat", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(orch, "_suspend_group_chat", AsyncMock(return_value=([], None, None)))
    stages, runtime_stages = [], []

    def _record_debug(stage, event, **extra):
        stages.append(stage)
        if extras is not None:
            extras.append((stage, extra))

    monkeypatch.setattr(orch, "_record_debug", _record_debug)

    async def observe(envelope):
        runtime_stages.append(envelope.stage)
        return envelope

    monkeypatch.setattr(orch._debug_helper, "_runtime_events", SimpleNamespace(dispatch_envelope=observe))
    queue = MessageQueue()
    event = orch.start_reply(
        message=_make_group_message() if kind == "group" else _make_private_message(),
        queue=queue, queue_key="888888" if kind == "group" else "10001", decision=_make_decision(),
    )
    assert event is not None
    try:
        await asyncio.wait_for(asyncio.gather(*tuple(orch._tasks)), timeout=5)
    finally:
        await orch.shutdown()
    return event, provider, sent, stages, runtime_stages, queue


@pytest.mark.parametrize("full_check", [True, False])
async def test_plain_prose_without_tool_is_cancelled_and_never_sent(monkeypatch, full_check):
    """没有 tool_calls 的正文不发送；已发过 reminder，最终取消而不是记错误。"""
    draft = "你好" if full_check else "很长的待审草稿" * 100
    extras: list = []
    event, provider, sent, stages, runtime_stages, queue = await run_script(
        monkeypatch,
        [{"content": draft, "tool_calls": []}, {"content": draft, "tool_calls": []}],
        full_check=full_check,
        extras=extras,
    )
    assert len(provider.calls) == 2
    assert "no_tool_call_reminder" in stages
    assert event.state is ReplyState.CANCELLED
    assert event.completed_at is not None
    assert event.error is None
    assert event.generated_text == ""
    assert event.send_response is None
    sent.assert_not_awaited()
    assert "unsent_prose_detected" in stages
    audit = dict(extras)["unsent_prose_detected"]
    assert audit["reply_text"] == draft
    assert "reply.cancel" in runtime_stages and "reply.complete" not in runtime_stages
    assert not queue.entries("888888")


@pytest.mark.parametrize("full_check", [True, False])
@pytest.mark.parametrize("review", ["或者就这句？简短自然", "cancel", ""])
async def test_review_without_tool_is_cancelled_and_never_sends_draft(monkeypatch, full_check, review):
    draft = "你好" if full_check else "很长的待审草稿" * 100
    first = tool_response("send_reply", {"text": draft})
    event, provider, sent, stages, runtime_stages, queue = await run_script(
        monkeypatch,
        [first, {"content": review, "tool_calls": []}, {"content": review, "tool_calls": []}],
        full_check=full_check,
    )
    assert len(provider.calls) == 3
    assert "no_tool_call_reminder" in stages
    assert event.state is ReplyState.CANCELLED
    assert event.completed_at is not None
    assert event.error is None
    assert event.generated_text == ""
    assert event.send_response is None
    sent.assert_not_awaited()
    assert "ai_reply_check_without_tool_call" in stages
    assert "reply.cancel" in runtime_stages and "reply.complete" not in runtime_stages
    assert not queue.entries("888888")


@pytest.mark.parametrize("kind", ["group", "private"])
@pytest.mark.parametrize("decision", ["send_reply", "cancel"])
async def test_structured_review_decisions_still_work(monkeypatch, kind, decision):
    args = {"text": "确认后的正文", "ai_check_approved": True} if decision == "send_reply" else {"reason": "无需参与"}
    event, provider, sent, stages, _, _ = await run_script(monkeypatch, [
        tool_response("send_reply", {"text": "待审草稿"}), tool_response(decision, args),
    ], kind=kind)
    expected_calls = 3 if decision == "send_reply" else 2
    assert len(provider.calls) == expected_calls
    assert "ai_reply_check_without_tool_call" not in stages
    if decision == "cancel":
        assert event.state is ReplyState.CANCELLED
        sent.assert_not_awaited()
    else:
        assert event.state is ReplyState.COMPLETED
        sent.assert_awaited_once()
        assert sent.await_args.args[1] == [{"type": "text", "data": {"text": "确认后的正文"}}]


@pytest.mark.parametrize("kind", ["group", "private"])
async def test_bare_cancel_in_plain_model_output_is_not_claimed_sent(monkeypatch, kind):
    event, provider, sent, stages, runtime_stages, _ = await run_script(
        monkeypatch,
        [{"content": "cancel", "tool_calls": []}, {"content": "cancel", "tool_calls": []}],
        full_check=False,
        kind=kind,
    )
    assert len(provider.calls) == 2
    assert "no_tool_call_reminder" in stages
    sent.assert_not_awaited()
    assert event.state is ReplyState.CANCELLED
    assert event.send_response is None
    assert event.error is None
    assert "unsent_prose_detected" in stages
    assert "reply.cancel" in runtime_stages and "reply.complete" not in runtime_stages


@pytest.mark.parametrize("text,segments", [
    ("cancel，是什么意思", ["cancel", "是什么意思"]),
    ("我选择\ncancel", ["我选择", "cancel"]),
])
async def test_orchestrator_forwards_verified_preview_to_real_sender(monkeypatch, text, segments):
    first = tool_response("send_reply", {"text": text})
    approved = tool_response("send_reply", {
        "text": text, "segments": segments, "ai_check_approved": True,
    })
    event, provider, sent, _, _, _ = await run_script(monkeypatch, [first, approved])
    assert event.state is ReplyState.COMPLETED
    assert len(provider.calls) == 3
    preview_text = "\n".join(str(message.get("content", "")) for message in provider.calls[1][0])
    assert "切分结果：" in preview_text
    assert all(f"{index}. {part}" in preview_text for index, part in enumerate(segments, 1))
    wire = [part["data"]["text"] for call in sent.await_args_list for part in call.args[1] if part["type"] == "text"]
    assert wire == segments


async def test_tool_review_pending_clears_only_on_successful_decision():
    send = AsyncMock(return_value=False)
    cancel = AsyncMock()
    executor = ReplyToolExecutor(send_reply_handler=send, cancel_handler=cancel, ai_reply_check=True)
    assert not executor.ai_check_pending
    result = await executor.execute("send_reply", {"text": "你好"})
    assert "暂未发送" in result and executor.ai_check_pending
    send.assert_not_awaited()
    result = await executor.execute("send_reply", {"text": "你好", "ai_check_approved": True})
    assert result.startswith("错误：") and executor.ai_check_pending
    send.return_value = True
    await executor.execute("send_reply", {"text": "你好", "ai_check_approved": True})
    assert not executor.ai_check_pending
    await executor.execute("send_reply", {"text": "下一条"})
    await executor.execute("cancel", {})
    assert not executor.ai_check_pending
    cancel.assert_awaited_once()
