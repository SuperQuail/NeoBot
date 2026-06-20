"""Tests for EventGateway — the unified event ingress replacing EventIngress."""

from __future__ import annotations

import pytest

from neobot_app.runtime.gateway import EventGateway
from neobot_app.runtime.event_context import EventContext


class _HookBus:
    def __init__(self) -> None:
        self.ctx = None

    async def dispatch(self, ctx: EventContext) -> None:
        self.ctx = ctx
        # Simulate plugin consumption test
        if ctx.raw_event.get("_test_mark_consumed"):
            ctx.consumed = True


class _LegacyPipeline:
    def __init__(self) -> None:
        self.received_private: list = []
        self.received_group: list = []

    async def handle_private_message_event(self, raw_event: dict, *, skip_ai_reply: bool = False) -> None:
        self.received_private.append({"raw_event": raw_event, "skip_ai_reply": skip_ai_reply})

    async def handle_group_message_event(self, raw_event: dict, *, skip_ai_reply: bool = False) -> None:
        self.received_group.append({"raw_event": raw_event, "skip_ai_reply": skip_ai_reply})

    async def flush_pending_summaries(self) -> None:
        pass


class _NoticeHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _RequestHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _LifecycleHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _Source:
    def subscribe(self, *args, **kwargs):
        raise AssertionError("not used in unit tests")


@pytest.mark.asyncio
async def test_event_gateway_honors_local_skip_ai_reply_marker() -> None:
    """Verify that _neobot_skip_ai_reply is stripped and passed as skip_ai_reply."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "_neobot_skip_ai_reply": True,
        "_local_conversation_name": "Alice",
    }
    await gateway.handle(raw_event)

    assert len(legacy.received_private) == 1
    handled = legacy.received_private[0]
    assert handled["skip_ai_reply"] is True
    assert "_neobot_skip_ai_reply" not in handled["raw_event"]
    assert "_local_conversation_name" not in handled["raw_event"]


@pytest.mark.asyncio
async def test_event_gateway_local_conversation_name_stripped() -> None:
    """Verify _local_conversation_name is stripped from the event and stored in metadata."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "group",
        "_local_conversation_name": "Bob",
    }
    await gateway.handle(raw_event)

    assert hooks.ctx is not None
    assert hooks.ctx.metadata.get("local_conversation_name") == "Bob"
    assert "_local_conversation_name" not in hooks.ctx.raw_event


@pytest.mark.asyncio
async def test_event_gateway_routes_notice_events() -> None:
    """Verify notice events are routed to the notice handler."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "notice",
        "notice_type": "group_poke",
    }
    await gateway.handle(raw_event)

    assert notice.ctx is not None
    assert notice.ctx.raw_event["post_type"] == "notice"
    assert len(legacy.received_private) == 0
    assert len(legacy.received_group) == 0


@pytest.mark.asyncio
async def test_event_gateway_respects_consumed_flag() -> None:
    """Verify consumed events are not routed to handlers."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "_test_mark_consumed": True,
    }
    await gateway.handle(raw_event)

    # The event should have been consumed by the plugin hook bus
    # and not forwarded to the legacy pipeline
    assert len(legacy.received_private) == 0
    assert len(legacy.received_group) == 0
