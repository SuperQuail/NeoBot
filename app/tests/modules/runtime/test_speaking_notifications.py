"""Actual hub/scheduler/reply paths must distinguish silence from delivery."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from neobot_adapter import LocalAdapter
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.runtime.notifications import BackgroundNotificationHub
from neobot_app.runtime.scheduled_tasks import ScheduledTaskConfig, ScheduledTaskManager
from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecord, ScheduledTaskRecurrence
from neobot_contracts.ports.speaking import SpeakingDecision, SpeechBlocked


class PromptBuilder:
    async def build_group_chat_prompt(self, **kwargs):
        return "Remind the user."

    async def build_group_chat_messages(self, **kwargs):
        return []


class Provider:
    def __init__(self, gate):
        self.gate = gate
        self.calls = 0

    async def chat(self, messages):
        self.calls += 1
        self.gate[0] = False
        return {"content": "Time to take a break."}

    async def close(self):
        pass


class Repository:
    def __init__(self, task):
        self.task = task
        self.archived = []

    async def list_active(self, **kwargs):
        return [self.task] if self.task is not None and not kwargs.get("offset") else []

    async def archive_completed(self, task_uuid, *, completion_reason, **kwargs):
        self.archived.append(completion_reason)
        self.task = None

    async def update(self, task_uuid, **kwargs):
        self.task = replace(self.task, **kwargs)


class UnitOfWork:
    def __init__(self, repository):
        self.scheduled_tasks = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        pass


def runtime(gate):
    adapter = LocalAdapter()
    policy = SpeakingPolicyRegistry()
    policy.register("speaking_schedule", lambda _: SpeakingDecision(gate[0], "closed"))
    adapter.core.speaking_policy = policy
    queue = MessageQueue()
    provider = Provider(gate)
    orchestrator = ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=PromptBuilder(),
        provider=provider,
        config=SimpleNamespace(chat=SimpleNamespace(reply_mode="common")),
        group_message_queue=queue,
    )
    hub = BackgroundNotificationHub(orchestrator=orchestrator)
    return adapter, provider, orchestrator, hub


@pytest.mark.asyncio
async def test_hub_closed_notification_is_not_consumed_or_queued():
    adapter, provider, orchestrator, hub = runtime([False])
    consumed = []
    try:
        with pytest.raises(SpeechBlocked):
            await hub.publish(
                source="scheduled_task",
                kind="group",
                conversation_id="42",
                content="break",
                on_consumed=lambda _: consumed.append(True),
            )
        assert consumed == []
        assert provider.calls == 0
        assert not orchestrator._tasks
        assert adapter.core.list_conversations() == []
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
        assert orchestrator._group_queue.entries("42") == []
    finally:
        await orchestrator.shutdown()


@pytest.mark.parametrize("initial_allow", [False, True])
@pytest.mark.parametrize("recurrence", [ScheduledTaskRecurrence.ONCE, ScheduledTaskRecurrence.DAILY])
@pytest.mark.asyncio
async def test_scheduler_policy_skip_is_not_sent_and_never_backfilled(initial_allow, recurrence):
    gate = [initial_allow]
    adapter, provider, orchestrator, hub = runtime(gate)
    now = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    task = ScheduledTaskRecord(
        id=1,
        task_uuid="policy-task",
        title="Break",
        detail="",
        recurrence=recurrence,
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=5),
        bindings=(ConversationRef("group", "42"),),
    )
    repository = Repository(task)
    manager = ScheduledTaskManager(
        uow_factory=lambda: UnitOfWork(repository), config=ScheduledTaskConfig(), notification_hub=hub
    )
    try:
        await manager.scan_due_tasks(now=now)
        if orchestrator._tasks:
            await asyncio.gather(*orchestrator._tasks)
        assert adapter.core.list_conversations() == []
        assert provider.calls == (1 if initial_allow else 0)
        assert manager._last_reminder_at == {}
        assert "one_shot_notification_sent" not in repository.archived
        if recurrence == ScheduledTaskRecurrence.ONCE:
            assert repository.archived == ["speaking_policy_skipped"]
        else:
            assert len(repository.task.completed_window_keys) == 1
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
        assert manager.get_pipeline_status("group:42")["scheduled_task_notifications_pending"] == 0
        gate[0] = True
        await manager.scan_due_tasks(now=now + timedelta(seconds=1))
        assert adapter.core.list_conversations() == []
        assert provider.calls == (1 if initial_allow else 0)
    finally:
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_agent_tool_denial_is_typed_and_stops_generation():
    gate = [True]
    adapter, _, orchestrator, hub = runtime(gate)

    class ToolProvider:
        calls = 0

        async def close(self):
            pass

        async def chat(self, messages, tools=None):
            self.calls += 1
            gate[0] = False
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "send",
                        "type": "function",
                        "function": {"name": "send_reply", "arguments": '{"text":"Take a break"}'},
                    }
                ],
            }

    provider = ToolProvider()
    orchestrator._provider = provider
    orchestrator._config.chat.reply_mode = "agent"
    try:
        with pytest.raises(SpeechBlocked):
            await hub.publish(source="scheduled_task", kind="group", conversation_id="42", content="break")
        assert provider.calls == 1
        assert adapter.core.list_conversations() == []
    finally:
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_speak_tool_does_not_swallow_policy_denial():
    from neobot_app.reply.tools import ReplyToolExecutor

    adapter, _, orchestrator, _ = runtime([False])

    async def speak(**kwargs):
        return await adapter.send(ConversationRef("group", "42"), "voice")

    executor = ReplyToolExecutor(tts_service=SimpleNamespace(enabled=True), speak_handler=speak)
    try:
        with pytest.raises(SpeechBlocked):
            await executor.execute("speak", {"text": "break"})
        assert adapter.core.list_conversations() == []
    finally:
        await executor.close()
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_policy_busy_pipeline_returns_without_queue_or_deadlock():
    _, _, orchestrator, hub = runtime([True])
    orchestrator._active_pipelines["group:42"] = asyncio.current_task()
    try:
        assert (
            await asyncio.wait_for(
                hub.publish(source="scheduled_task", kind="group", conversation_id="42", content="break"), 0.5
            )
            is False
        )
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
        assert orchestrator._group_queue.entries("42") == []
    finally:
        orchestrator._active_pipelines.clear()
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_empty_registry_preserves_queued_acceptance():
    _, _, orchestrator, hub = runtime([True])
    orchestrator._adapter.core.speaking_policy = SpeakingPolicyRegistry()
    orchestrator._active_pipelines["group:42"] = asyncio.current_task()
    try:
        assert await hub.publish(source="scheduled_task", kind="group", conversation_id="42", content="break") is False
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 1
        assert orchestrator._group_queue.entries("42")
    finally:
        orchestrator._active_pipelines.clear()
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_allowed_notification_consumes_only_after_delivery():
    _, _, orchestrator, hub = runtime([True])
    started, release = asyncio.Event(), asyncio.Event()

    class DelayedProvider:
        async def chat(self, messages):
            started.set()
            await release.wait()
            return {"content": "Take a break"}

        async def close(self):
            pass

    orchestrator._provider = DelayedProvider()
    consumed = []
    publish = asyncio.create_task(
        hub.publish(
            source="scheduled_task",
            kind="group",
            conversation_id="42",
            content="break",
            on_consumed=lambda _: consumed.append(True),
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert not publish.done()
        assert consumed == []
        release.set()
        assert await asyncio.wait_for(publish, 1) is True
        assert consumed == [True]
    finally:
        release.set()
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_notification_timeout_cancels_pending_send(monkeypatch):
    adapter, _, orchestrator, hub = runtime([True])

    class StalledProvider:
        async def chat(self, messages):
            await asyncio.Event().wait()

        async def close(self):
            pass

    orchestrator._provider = StalledProvider()
    monkeypatch.setattr(orchestrator, "_get_prompt_timeout_seconds", lambda: 0.02)
    monkeypatch.setattr(orchestrator, "_get_model_response_timeout_seconds", lambda event: 0.02)
    monkeypatch.setattr(orchestrator, "_get_io_timeout_seconds", lambda: 0.02)
    try:
        assert (
            await asyncio.wait_for(
                hub.publish(source="scheduled_task", kind="group", conversation_id="42", content="break"), 1
            )
            is False
        )
        assert not orchestrator._tasks
        assert adapter.core.list_conversations() == []
        assert hub.get_pipeline_status("group:42")["background_notifications_pending"] == 0
    finally:
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_scheduler_without_hub_still_propagates_policy_skip():
    adapter, _, orchestrator, _ = runtime([False])
    now = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    task = ScheduledTaskRecord(
        id=1,
        task_uuid="no-hub",
        title="Break",
        detail="",
        recurrence=ScheduledTaskRecurrence.ONCE,
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=5),
        bindings=(ConversationRef("group", "42"),),
    )
    repository = Repository(task)
    manager = ScheduledTaskManager(uow_factory=lambda: UnitOfWork(repository))
    manager.set_orchestrator(orchestrator)
    try:
        await manager.scan_due_tasks(now=now)
        assert repository.archived == ["speaking_policy_skipped"]
        assert manager._last_reminder_at == {}
        assert adapter.core.list_conversations() == []
    finally:
        await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_mixed_bindings_skip_window_without_backfill():
    adapter, _, orchestrator, hub = runtime([True])
    policy = SpeakingPolicyRegistry()
    policy.register("schedule", lambda ref: SpeakingDecision(ref.id != "42", "closed"))
    adapter.core.speaking_policy = policy

    class AllowedProvider:
        calls = 0

        async def chat(self, messages):
            self.calls += 1
            return {"content": "Break"}

        async def close(self):
            pass

    orchestrator._provider = AllowedProvider()
    now = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    task = ScheduledTaskRecord(
        id=1,
        task_uuid="mixed",
        title="Break",
        detail="",
        recurrence=ScheduledTaskRecurrence.DAILY,
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=5),
        bindings=(ConversationRef("group", "42"), ConversationRef("group", "43")),
        metadata={"one_shot_notification": False},
    )
    repository = Repository(task)
    manager = ScheduledTaskManager(uow_factory=lambda: UnitOfWork(repository), notification_hub=hub)
    try:
        await manager.scan_due_tasks(now=now)
        assert len(repository.task.completed_window_keys) == 1
        adapter.core.speaking_policy = SpeakingPolicyRegistry()
        await manager.scan_due_tasks(now=now + timedelta(seconds=1))
        assert orchestrator._provider.calls == 1
    finally:
        await orchestrator.shutdown()
