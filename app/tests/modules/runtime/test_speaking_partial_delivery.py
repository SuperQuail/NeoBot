"""A denied later fragment must preserve the first real delivery."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter import LocalAdapter
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.runtime.notifications import BackgroundNotificationHub
from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.speaking import SpeakingDecision, SpeechBlocked


class PromptBuilder:
    async def build_group_chat_prompt(self, **kwargs):
        return "Reply to the user."

    async def build_group_chat_messages(self, **kwargs):
        return []


@pytest.mark.parametrize("mode,kind", [("common", "text"), ("agent", "text"), ("agent", "image"), ("agent", "long")])
@pytest.mark.parametrize("notification", [False, True])
async def test_partial_send_preserves_receipt_lifecycle_and_cooldown(tmp_path, monkeypatch, mode, kind, notification):
    monkeypatch.setattr("neobot_app.reply.sender._default_self_sent_uow_factory", lambda: None)
    adapter = LocalAdapter()
    policy = SpeakingPolicyRegistry()
    policy.register("schedule", lambda _: SpeakingDecision(not adapter.core.list_conversations(), "now quiet"))
    adapter.core.speaking_policy = policy
    text = "第一句话。\n第二句话。"
    image = tmp_path / "fixture.png"
    image.write_bytes(b"offline image fixture")

    class Provider:
        calls = 0

        async def chat(self, messages, tools=None):
            self.calls += 1
            assert self.calls == 1
            if mode == "common":
                return {"content": text}
            args = {"text": text, **({"images": [1]} if kind == "image" else {})}
            if kind == "long":
                args = {"image_path": str(image), "caption": "说明文字", "markdown": "# Long reply"}
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "send",
                        "type": "function",
                        "function": {
                            "name": "send_long_reply" if kind == "long" else "send_reply",
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }

        async def close(self):
            pass

    queue = MessageQueue()
    provider = Provider()
    orchestrator = ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=PromptBuilder(),
        provider=provider,
        config=SimpleNamespace(chat=SimpleNamespace(reply_mode=mode)),
        group_message_queue=queue,
        file_server=SimpleNamespace(_enabled=False),
        markdown_image_converter=SimpleNamespace() if kind == "long" else None,
    )
    orchestrator._sender._sentence_cooldown = 0
    if kind == "image":
        orchestrator._sender._emoji_service = SimpleNamespace(
            get_entry=lambda _: SimpleNamespace(file_path=image),
            record_usage=AsyncMock(),
        )
    lifecycle = []
    original_emit = orchestrator._emit_runtime_event

    async def capture(name, event, **kwargs):
        lifecycle.append((name, event))
        return await original_emit(name, event, **kwargs)

    monkeypatch.setattr(orchestrator, "_emit_runtime_event", capture)
    hub = BackgroundNotificationHub(orchestrator=orchestrator)
    consumed = []
    try:
        if notification:
            with pytest.raises(SpeechBlocked):
                await hub.publish(
                    source="scheduled_task",
                    kind="group",
                    conversation_id="42",
                    content="break",
                    on_consumed=lambda _: consumed.append(True),
                )
        else:
            event = ReplyEvent(mode=mode, conversation_ref=ConversationRef("group", "42"), pre_reply_message_id=41)
            await orchestrator._run(event, queue, "42")
            assert queue.get_last_reply_position("42") == 41, (event.state, event.error, provider.calls)
        messages = adapter.core.list_messages(kind="group", conversation_id="42")["messages"]
        assert len(messages) == 1
        event = lifecycle[-1][1]
        assert event.state is ReplyState.COMPLETED
        assert event.send_response is not None
        assert event.error is None
        assert isinstance(event.speech_blocked, SpeechBlocked)
        assert orchestrator._last_reply_time["group:42"] > 0
        names = [name for name, _ in lifecycle]
        assert names.count("reply.complete") == 1
        assert "reply.cancel" not in names
        assert "reply.fail" not in names
        assert provider.calls == 1
        assert consumed == []
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
        assert all(entry.notification is None for entry in queue.entries("42"))
    finally:
        await orchestrator.shutdown()


@pytest.mark.parametrize("mode", ["common", "agent"])
@pytest.mark.parametrize("partial", [True, False])
async def test_notification_timeout_confirms_only_a_complete_send(monkeypatch, mode, partial):
    monkeypatch.setattr("neobot_app.reply.sender._default_self_sent_uow_factory", lambda: None)
    adapter = LocalAdapter()
    policy = SpeakingPolicyRegistry()
    policy.register("schedule", lambda _: SpeakingDecision(not adapter.core.list_conversations(), "now quiet"))
    adapter.core.speaking_policy = policy
    first_delivery, after_send = asyncio.Event(), asyncio.Event()

    class Events:
        async def dispatch_envelope(self, envelope):
            if envelope.stage == "reply.send.after" and not partial:
                after_send.set()
                await asyncio.Event().wait()
            return envelope

    class Provider:
        async def chat(self, messages, tools=None):
            text = "第一句话。\n第二句话。" if partial else "完整回复"
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
        runtime_events=Events(),
    )
    orchestrator._sender._sentence_cooldown = 3600
    orchestrator._get_prompt_timeout_seconds = lambda: 0.02
    orchestrator._get_model_response_timeout_seconds = lambda _: 0.02
    orchestrator._get_io_timeout_seconds = lambda: 0.02
    record_delivery = orchestrator._record_reply_delivered

    def record_and_signal(*args, **kwargs):
        record_delivery(*args, **kwargs)
        first_delivery.set()

    monkeypatch.setattr(orchestrator, "_record_reply_delivered", record_and_signal)
    wait_delivery = orchestrator.wait_reply_delivery

    async def wait_after_first_delivery(event):
        await asyncio.wait_for(first_delivery.wait(), timeout=2)
        if not partial:
            await asyncio.wait_for(after_send.wait(), timeout=2)
        return await wait_delivery(event)

    monkeypatch.setattr(orchestrator, "wait_reply_delivery", wait_after_first_delivery)
    lifecycle = []
    emit = orchestrator._emit_runtime_event

    async def capture(name, event, **kwargs):
        lifecycle.append((name, event))
        return await emit(name, event, **kwargs)

    monkeypatch.setattr(orchestrator, "_emit_runtime_event", capture)
    hub = BackgroundNotificationHub(orchestrator=orchestrator)
    consumed = []
    try:
        result = await hub.publish(
            source="scheduled_task",
            kind="group",
            conversation_id="42",
            content="break",
            on_consumed=lambda _: consumed.append(True),
        )
        assert result is (not partial)
        assert consumed == ([] if partial else [True])
        assert len(adapter.core.list_messages(kind="group", conversation_id="42")["messages"]) == 1
        event = lifecycle[-1][1]
        assert event.state is ReplyState.COMPLETED
        assert event.send_response is not None
        assert event.error is None
        assert event.speech_blocked is None
        names = [name for name, _ in lifecycle]
        assert names.count("reply.complete") == 1
        assert "reply.cancel" not in names
        assert "reply.fail" not in names
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
    finally:
        await orchestrator.shutdown()
