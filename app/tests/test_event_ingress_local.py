from __future__ import annotations

import pytest

from neobot_app.runtime.event_ingress import EventIngress


class _HookBus:
    def __init__(self) -> None:
        self.ctx = None

    async def dispatch(self, ctx):
        self.ctx = ctx


class _Router:
    def __init__(self) -> None:
        self.ctx = None

    async def route(self, ctx):
        self.ctx = ctx


class _Source:
    def subscribe(self, *args, **kwargs):
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_event_ingress_honors_local_skip_ai_reply_marker() -> None:
    hooks = _HookBus()
    router = _Router()
    ingress = EventIngress(event_source=_Source(), hook_bus=hooks, router=router)

    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "_neobot_skip_ai_reply": True,
        "_local_conversation_name": "Alice",
    }
    await ingress.handle(raw_event)

    assert router.ctx is not None
    assert router.ctx.skip_ai_reply is True
    assert router.ctx.metadata["local_conversation_name"] == "Alice"
    assert "_neobot_skip_ai_reply" not in router.ctx.raw_event
    assert "_neobot_skip_ai_reply" in raw_event
