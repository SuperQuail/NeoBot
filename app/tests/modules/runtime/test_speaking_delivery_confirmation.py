"""Notification confirmation follows delivery, independently of bookkeeping."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter import LocalAdapter
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.event import ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.runtime.notifications import BackgroundNotificationHub
from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
from neobot_contracts.ports.speaking import SpeakingDecision, SpeechBlocked
from neobot_modloader.hooks import PluginHookBus


class PromptBuilder:
    async def build_group_chat_prompt(self, **kwargs):
        return "Reply to the user."

    async def build_group_chat_messages(self, **kwargs):
        return []


@pytest.mark.parametrize(
    "kind,images,stall_at,complete",
    [
        ("emoji", [1], 1, True),
        ("emoji", [1, 2], 1, False),
        ("emoji", [1, 2], 2, True),
        ("emoji", [1, 99], 1, True),
        ("markdown", [], 1, True),
        ("long", [], 1, True),
    ],
)
async def test_media_confirmation_survives_stalled_image_index(tmp_path, monkeypatch, kind, images, stall_at, complete):
    monkeypatch.setattr("neobot_app.reply.sender._default_self_sent_uow_factory", lambda: None)
    adapter = LocalAdapter()
    policy = SpeakingPolicyRegistry()
    policy.register("schedule", lambda _: SpeakingDecision(True))
    adapter.core.speaking_policy = policy
    image = tmp_path / "offline.png"
    image.write_bytes(b"offline fixture")
    registrar_entered = asyncio.Event()
    registrations = 0

    async def register(_):
        nonlocal registrations
        registrations += 1
        if registrations == stall_at:
            registrar_entered.set()
            await asyncio.Event().wait()
        return "tmp_offline"

    class Provider:
        async def chat(self, messages, tools=None):
            if kind == "markdown":
                return {"content": "完整的 Markdown 回复"}
            name = "send_long_reply" if kind == "long" else "send_reply"
            args = {"image_path": str(image)} if kind == "long" else {"text": "cancel", "images": images}
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "send",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }

        async def close(self):
            pass

    orchestrator = ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=PromptBuilder(),
        provider=Provider(),
        config=SimpleNamespace(chat=SimpleNamespace(reply_mode="common" if kind == "markdown" else "agent")),
        group_message_queue=MessageQueue(),
        file_server=SimpleNamespace(_enabled=False),
        markdown_image_converter=SimpleNamespace(convert=AsyncMock(return_value=image)),
    )
    orchestrator._sender._emoji_service = SimpleNamespace(
        get_entry=lambda number: SimpleNamespace(file_path=image) if number != 99 else None,
        record_usage=AsyncMock(),
    )
    orchestrator._sender._image_registrar = register
    orchestrator._sender._long_reply_max_length = 1
    orchestrator._get_prompt_timeout_seconds = lambda: 0.02
    orchestrator._get_model_response_timeout_seconds = lambda _: 0.02
    orchestrator._get_io_timeout_seconds = lambda: 0.02
    wait_delivery = orchestrator.wait_reply_delivery

    async def wait_after_registration(event):
        await asyncio.wait_for(registrar_entered.wait(), timeout=2)
        return await wait_delivery(event)

    monkeypatch.setattr(orchestrator, "wait_reply_delivery", wait_after_registration)
    lifecycle = []
    emit = orchestrator._emit_runtime_event

    async def capture(name, event, **kwargs):
        lifecycle.append((name, event))
        return await emit(name, event, **kwargs)

    monkeypatch.setattr(orchestrator, "_emit_runtime_event", capture)
    consumed = []
    try:
        result = await BackgroundNotificationHub(orchestrator=orchestrator).publish(
            source="scheduled_task",
            kind="group",
            conversation_id="42",
            content="break",
            on_consumed=lambda _: consumed.append(True),
        )
        assert result is complete
        assert consumed == ([True] if complete else [])
        assert len(adapter.core.list_messages(kind="group", conversation_id="42")["messages"]) == stall_at
        event = lifecycle[-1][1]
        assert event.state is ReplyState.COMPLETED
        assert event.send_response is not None
        assert event.send_incomplete is (not complete)
        assert event.error is None
        assert [name for name, _ in lifecycle if name in {"reply.complete", "reply.cancel", "reply.fail"}] == [
            "reply.complete"
        ]
    finally:
        await orchestrator.shutdown()


@pytest.mark.parametrize("mode", ["common", "agent"])
@pytest.mark.parametrize("blocked", [False, True])
async def test_completion_hook_timeout_keeps_confirmation_and_dispatches_once(monkeypatch, mode, blocked):
    monkeypatch.setattr("neobot_app.reply.sender._default_self_sent_uow_factory", lambda: None)
    adapter = LocalAdapter()
    policy = SpeakingPolicyRegistry()
    policy.register(
        "schedule", lambda _: SpeakingDecision(not blocked or not adapter.core.list_conversations(), "now quiet")
    )
    adapter.core.speaking_policy = policy
    completing = asyncio.Event()

    complete_calls = 0

    async def on_complete(envelope):
        nonlocal complete_calls
        complete_calls += 1
        completing.set()
        if complete_calls == 1:
            await asyncio.Event().wait()

    events = PluginHookBus()
    events.subscribe_runtime(on_complete, stage="reply.complete")

    class Provider:
        calls = 0

        async def chat(self, messages, tools=None):
            self.calls += 1
            if mode == "agent" and self.calls > 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "cancel",
                            "type": "function",
                            "function": {
                                "name": "cancel",
                                "arguments": None,
                            },
                        }
                    ],
                }
            text = "第一句话。\n第二句话。" if blocked else "完整回复"
            if mode == "common":
                return {"content": text}
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "send",
                        "type": "function",
                        "function": {
                            "name": "send_reply",
                            "arguments": json.dumps({"text": text}),
                        },
                    }
                ],
            }

        async def close(self):
            pass

    orchestrator = ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=PromptBuilder(),
        provider=Provider(),
        config=SimpleNamespace(chat=SimpleNamespace(reply_mode=mode)),
        group_message_queue=MessageQueue(),
        runtime_events=events,
    )
    orchestrator._sender._sentence_cooldown = 0
    orchestrator._get_prompt_timeout_seconds = lambda: 0.02
    orchestrator._get_model_response_timeout_seconds = lambda _: 0.02
    orchestrator._get_io_timeout_seconds = lambda: 0.02
    wait_delivery = orchestrator.wait_reply_delivery
    captured = []

    async def wait_after_completion(event):
        captured.append(event)
        await asyncio.wait_for(completing.wait(), timeout=2)
        return await wait_delivery(event)

    monkeypatch.setattr(orchestrator, "wait_reply_delivery", wait_after_completion)
    consumed = []
    try:
        publish = BackgroundNotificationHub(orchestrator=orchestrator).publish(
            source="scheduled_task",
            kind="group",
            conversation_id="42",
            content="break",
            on_consumed=lambda _: consumed.append(True),
        )
        if blocked:
            with pytest.raises(SpeechBlocked, match="now quiet"):
                await publish
        else:
            assert await publish is True
        assert consumed == ([] if blocked else [True])
        assert len(adapter.core.list_messages(kind="group", conversation_id="42")["messages"]) == 1
        assert captured[0].state is ReplyState.COMPLETED
        assert captured[0].send_response is not None
        assert isinstance(captured[0].speech_blocked, SpeechBlocked) is blocked
        assert complete_calls == 1
    finally:
        await orchestrator.shutdown()
