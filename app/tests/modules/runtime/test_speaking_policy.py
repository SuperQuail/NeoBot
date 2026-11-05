"""Policy gates exercise real registries and adapter transports."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from neobot_adapter import LocalAdapter, OneBotAdapter
from neobot_contracts.models import ConversationRef


def policy_types():
    # Missing implementation must fail as an assertion, rather than collection error.
    spec = importlib.util.find_spec("neobot_app.runtime.speaking_policy")
    assert spec is not None, "speaking policy registry is not implemented"
    from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
    from neobot_contracts.ports.speaking import SpeakingDecision, SpeechBlocked

    return SpeakingPolicyRegistry, SpeakingDecision, SpeechBlocked


def test_registry_intersection_unregister_and_owner_bypass():
    Registry, Decision, _ = policy_types()
    registry = Registry()
    conv = ConversationRef("group", "42")
    assert registry.evaluate(conv).allowed
    remove_a = registry.register("a", lambda _: Decision(False, "a closed"))
    remove_b = registry.register("b", lambda _: Decision(False, "b closed"))
    assert registry.evaluate(conv).reason == "a closed"
    with registry.bypass("a"):
        assert registry.evaluate(conv).reason == "b closed"
        with registry.bypass("b"):
            assert registry.evaluate(conv).allowed
        assert not registry.evaluate(conv).allowed
    remove_a()
    remove_a()
    assert registry.evaluate(conv).reason == "b closed"
    remove_b()
    assert registry.evaluate(conv).allowed


@pytest.mark.asyncio
async def test_bypass_does_not_leak_to_concurrent_task():
    Registry, Decision, _ = policy_types()
    registry = Registry()
    registry.register("a", lambda _: Decision(False))
    conv = ConversationRef("private", "7")
    entered, release = asyncio.Event(), asyncio.Event()

    async def bypassed():
        with registry.bypass("a"):
            entered.set()
            await release.wait()
            assert registry.evaluate(conv).allowed

    task = asyncio.create_task(bypassed())
    await entered.wait()
    assert not registry.evaluate(conv).allowed
    release.set()
    await task


class Wire:
    def __init__(self):
        self.packets = []

    async def send(self, packet):
        self.packets.append(packet)


@pytest.mark.parametrize("adapter_type", [LocalAdapter, OneBotAdapter])
@pytest.mark.parametrize(
    "action,params",
    [
        ("send_private_msg", {"user_id": 7, "message": "hi"}),
        ("send_group_msg", {"group_id": 42, "message": [{"type": "image", "data": {"file": "x"}}]}),
        ("send_group_msg", {"group_id": 42, "message": [{"type": "record", "data": {"file": "x"}}]}),
        ("send_private_msg", {"user_id": 7, "message": [{"type": "file", "data": {"file": "x"}}]}),
        ("send_group_forward_msg", {"group_id": 42, "messages": []}),
        ("send_private_forward_msg", {"user_id": 7, "messages": []}),
        ("send_msg", {"message_type": "group", "group_id": 42, "message": "hi"}),
        ("upload_group_file", {"group_id": 42, "file": "x"}),
        ("upload_private_file", {"user_id": 7, "file": "x"}),
        ("send_group_ai_record", {"group_id": 42, "text": "hi"}),
    ],
)
@pytest.mark.asyncio
async def test_raw_send_families_block_before_side_effects(adapter_type, action, params):
    Registry, Decision, Blocked = policy_types()
    registry = Registry()
    seen = []
    registry.register("schedule", lambda conv: (seen.append(conv), Decision(False, "closed"))[1])
    adapter = adapter_type()
    adapter.core.speaking_policy = registry
    wire = Wire()
    if isinstance(adapter, OneBotAdapter):
        adapter.core.active_connections.add(wire)
    with pytest.raises(Blocked, match="closed"):
        await adapter.call_api(action, params, wait_response=False)
    assert len(seen) == 1
    assert wire.packets == []
    if isinstance(adapter, LocalAdapter):
        assert adapter.core.list_conversations() == []


@pytest.mark.parametrize("adapter_type", [LocalAdapter, OneBotAdapter])
@pytest.mark.asyncio
async def test_standard_send_evaluated_once_and_allow_reaches_transport(adapter_type):
    Registry, Decision, _ = policy_types()
    registry = Registry()
    seen = []
    registry.register("schedule", lambda conv: (seen.append(conv), Decision(True))[1])
    adapter = adapter_type()
    adapter.core.speaking_policy = registry
    wire = Wire()
    if isinstance(adapter, OneBotAdapter):
        adapter.core.active_connections.add(wire)
    await adapter.send(ConversationRef("group", "42"), "hello", wait_response=False)
    assert seen == [ConversationRef("group", "42")]
    if isinstance(adapter, OneBotAdapter):
        assert len(wire.packets) == 1
    else:
        messages = adapter.core.list_messages(kind="group", conversation_id="42")
        assert len(messages["messages"]) == 1


@pytest.mark.asyncio
async def test_local_direct_send_is_guarded():
    Registry, Decision, Blocked = policy_types()
    adapter = LocalAdapter()
    adapter.core.speaking_policy = Registry()
    adapter.core.speaking_policy.register("schedule", lambda _: Decision(False, "closed"))
    with pytest.raises(Blocked):
        await adapter.core.send(ConversationRef("private", "7"), "hello")
    assert adapter.core.list_conversations() == []


@pytest.mark.asyncio
async def test_non_message_actions_do_not_evaluate():
    Registry, _, _ = policy_types()
    adapter = OneBotAdapter()
    adapter.core.speaking_policy = Registry()

    def reject_evaluation(_):
        pytest.fail("non-message action was evaluated")

    adapter.core.speaking_policy.register("schedule", reject_evaluation)
    for action, params in [("send_like", {"user_id": 7}), ("get_group_list", {})]:
        assert await adapter.call_api(action, params) is None


@pytest.mark.asyncio
async def test_run_rejects_before_ai_and_reports_cancelled():
    Registry, Decision, _ = policy_types()
    from neobot_app.reply.orchestrator import ReplyOrchestrator
    from neobot_app.reply.event import ReplyEvent, ReplyState

    registry = Registry()
    registry.register("schedule", lambda _: Decision(False, "closed"))
    adapter = LocalAdapter()
    adapter.core.speaking_policy = registry
    orchestrator = ReplyOrchestrator(adapter=adapter, prompt_builder=SimpleNamespace())
    event = ReplyEvent(conversation_ref=ConversationRef("private", "7"))
    await orchestrator._run(event, SimpleNamespace(), "7")
    assert event.state is ReplyState.CANCELLED
    assert "closed" in event.error
    assert event.send_response is None


def test_host_exposes_same_registry_on_reuse():
    from neobot_app.bootstrap import _reuse_or, enable_core_reuse, disable_core_reuse
    from neobot_app.bootstrap._pipeline import build_plugin_host
    from neobot_contracts.ports.logging import NullLogger

    factory = SimpleNamespace(get_logger=lambda _: NullLogger())
    enable_core_reuse()
    try:
        first = _reuse_or("plugin", lambda: build_plugin_host(logger_factory=factory))
        second = _reuse_or("plugin", lambda: build_plugin_host(logger_factory=factory))
        assert first["host_facade"].services.get("speaking_policy") is first["speaking_policy"]
        assert second["speaking_policy"] is first["speaking_policy"]
    finally:
        disable_core_reuse()


@pytest.mark.asyncio
async def test_inherited_bypass_is_revoked_when_scope_exits():
    Registry, Decision, _ = policy_types()
    registry = Registry()
    registry.register("a", lambda _: Decision(False, "closed"))
    release = asyncio.Event()

    async def later():
        await release.wait()
        return registry.evaluate(ConversationRef("group", "42")).allowed

    with registry.bypass("a"):
        task = asyncio.create_task(later())
    release.set()
    assert await task is False


@pytest.mark.asyncio
async def test_bypass_exception_restores_policy_and_other_registry_isolated():
    Registry, Decision, _ = policy_types()
    first, second = Registry(), Registry()
    for registry in (first, second):
        registry.register("a", lambda _: Decision(False))
    conv = ConversationRef("group", "42")
    with pytest.raises(ValueError):
        with first.bypass("a"):
            assert first.evaluate(conv).allowed
            assert not second.evaluate(conv).allowed
            raise ValueError("command failed")
    assert not first.evaluate(conv).allowed


@pytest.mark.asyncio
async def test_request_proxy_and_websocket_api_are_guarded():
    Registry, Decision, Blocked = policy_types()
    from neobot_adapter.request._proxy import bind_core, unbind_core
    from neobot_adapter.request.message import send_group_forward_msg

    adapter = OneBotAdapter()
    adapter.core.speaking_policy = Registry()
    adapter.core.speaking_policy.register("a", lambda _: Decision(False, "closed"))
    bind_core(adapter.core)
    try:
        with pytest.raises(Blocked):
            await send_group_forward_msg(42, [])
        with pytest.raises(Blocked):
            await adapter.api.send_private_msg(7, "hello")
        with pytest.raises(Blocked):
            await adapter.api.send_message({"action": "send_group_msg", "params": {"group_id": 42, "message": "hello"}})
    finally:
        unbind_core()


def test_onebot_cross_thread_sync_propagates_bypass_and_denial():
    Registry, Decision, Blocked = policy_types()
    from threading import Event, Thread

    adapter = OneBotAdapter()
    registry = Registry()
    adapter.core.speaking_policy = registry
    remove = registry.register("schedule", lambda _: Decision(False, "closed"))
    wire = Wire()
    ready = Event()

    def receive_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        adapter.core.loop = loop
        adapter.core.active_connections.add(wire)
        loop.call_soon(ready.set)
        loop.run_forever()
        loop.close()

    thread = Thread(target=receive_loop)
    thread.start()
    assert ready.wait(5)
    try:
        with pytest.raises(Blocked, match="closed"):
            adapter.api.call_api_sync("send_group_msg", {"group_id": 42, "message": "hello"})
        with registry.bypass("schedule"):
            assert adapter.api.send_message_sync(
                {"action": "send_group_msg", "params": {"group_id": 42, "message": "hello"}}
            )
            other = registry.register("other", lambda _: Decision(False, "other closed"))
            with pytest.raises(Blocked, match="other closed"):
                adapter.api.call_api_sync("send_group_msg", {"group_id": 42, "message": "hello"})
            other()
        assert len(wire.packets) == 1
        remove()
    finally:
        adapter.core.loop.call_soon_threadsafe(adapter.core.loop.stop)
        thread.join(5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_policy_denial_does_not_change_sleep_or_standby_state():
    Registry, Decision, _ = policy_types()
    from neobot_app.runtime.sleep_service import SleepService
    from neobot_app.runtime.standby_service import StandbyService
    from neobot_app.reply.orchestrator import ReplyOrchestrator
    from neobot_app.reply.event import ReplyEvent, ReplyState

    sleep = SleepService()
    sleep.sleep(3600)
    standby = StandbyService(start_in_standby=True)
    sleep_before = vars(sleep).copy()
    standby_before = vars(standby).copy()
    adapter = LocalAdapter()
    adapter.core.speaking_policy = Registry()
    adapter.core.speaking_policy.register("schedule", lambda _: Decision(False, "closed"))
    orchestrator = ReplyOrchestrator(
        adapter=adapter, prompt_builder=SimpleNamespace(), sleep_service=sleep, standby_service=standby
    )
    event = ReplyEvent(conversation_ref=ConversationRef("group", "42"))
    await orchestrator._run(event, SimpleNamespace(), "42")
    assert event.state is ReplyState.CANCELLED
    assert vars(sleep) == sleep_before
    assert vars(standby) == standby_before


@pytest.mark.asyncio
async def test_send_fence_rechecks_after_early_allow_without_success_receipt():
    Registry, Decision, Blocked = policy_types()
    from neobot_app.reply.sender import ReplySender
    from neobot_app.reply.event import ReplyEvent, ReplyState

    registry = Registry()
    conv = ConversationRef("private", "7")
    assert registry.evaluate(conv).allowed
    # Simulate a schedule boundary crossing while the model is generating.
    registry.register("schedule", lambda _: Decision(False, "now closed"))
    adapter = LocalAdapter()
    adapter.core.speaking_policy = registry
    sender = ReplySender(adapter=adapter, file_server=None)
    event = ReplyEvent(conversation_ref=conv, state=ReplyState.GENERATING)
    with pytest.raises(Blocked, match="now closed"):
        await sender.send_reply(event, "Hello", send_original=True)
    assert event.send_response is None
    assert event.state is not ReplyState.COMPLETED
    assert adapter.core.list_conversations() == []


@pytest.mark.asyncio
async def test_allowed_local_forward_evaluated_once():
    Registry, Decision, _ = policy_types()
    registry = Registry()
    seen = []
    registry.register("schedule", lambda conv: (seen.append(conv), Decision(True))[1])
    adapter = LocalAdapter()
    adapter.core.speaking_policy = registry
    result = await adapter.call_api("send_private_forward_msg", {"user_id": 7, "messages": []})
    assert result["status"] == "ok"
    assert seen == [ConversationRef("private", "7")]
    assert len(adapter.core.list_messages(kind="private", conversation_id="7")["messages"]) == 1
