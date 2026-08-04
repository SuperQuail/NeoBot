from __future__ import annotations

from typing import Any

import pytest

from neobot_app.runtime.event_context import EventContext
from neobot_app.runtime.gateway import EventGateway


class _FakeSubscription:
    """记录退订调用的假订阅对象。"""

    def __init__(self, on_unsubscribe) -> None:
        self._on_unsubscribe = on_unsubscribe
        self._active = True

    def unsubscribe(self) -> None:
        if self._active:
            self._active = False
            self._on_unsubscribe()


class _FakeEventSource:
    """记录 subscribe/退订事件类型的假事件源。"""

    def __init__(self) -> None:
        self.subscribed: list[tuple[str, Any]] = []
        self.unsubscribed: list[tuple[str, Any]] = []

    def subscribe(self, event_type: str, handler) -> _FakeSubscription:
        record = (event_type, handler)
        self.subscribed.append(record)
        return _FakeSubscription(lambda: self.unsubscribed.append(record))


class _FakeLegacy:
    """记录私聊/群消息转发调用的假 legacy pipeline。"""

    def __init__(self) -> None:
        self.private_calls: list[tuple[dict, bool]] = []
        self.group_calls: list[tuple[dict, bool]] = []
        self.flush_calls = 0

    async def handle_private_message_event(self, event, *, skip_ai_reply=False) -> None:
        self.private_calls.append((event, skip_ai_reply))

    async def handle_group_message_event(self, event, *, skip_ai_reply=False) -> None:
        self.group_calls.append((event, skip_ai_reply))

    async def flush_pending_summaries(self) -> None:
        self.flush_calls += 1


class _FakeHookBus:
    """可选地消费事件的假插件钩子总线。"""

    def __init__(self, consumed: bool = False) -> None:
        self._consumed = consumed
        self.dispatched: list[EventContext] = []

    async def dispatch(self, ctx: EventContext) -> None:
        self.dispatched.append(ctx)
        if self._consumed:
            ctx.consume()


class _FakeHandler:
    """记录 handle 调用次数的假 notice/request/lifecycle 处理器。"""

    def __init__(self) -> None:
        self.calls: list[EventContext] = []

    async def handle(self, ctx: EventContext) -> None:
        self.calls.append(ctx)


def _make_gateway(
    source: _FakeEventSource | None = None,
    hook_bus: _FakeHookBus | None = None,
    legacy: _FakeLegacy | None = None,
    notice: _FakeHandler | None = None,
    request: _FakeHandler | None = None,
    lifecycle: _FakeHandler | None = None,
) -> tuple[EventGateway, _FakeEventSource, _FakeLegacy]:
    """构造仅依赖 Fake 组件的 EventGateway，并返回关键引用供断言。"""
    source = source or _FakeEventSource()
    legacy = legacy or _FakeLegacy()
    gateway = EventGateway(
        event_source=source,
        hook_bus=hook_bus or _FakeHookBus(),
        legacy_pipeline=legacy,
        notice_handler=notice or _FakeHandler(),
        request_handler=request or _FakeHandler(),
        lifecycle_handler=lifecycle or _FakeHandler(),
    )
    return gateway, source, legacy


def test_gateway_start_subscribes_all_event_types() -> None:
    """start 时必须订阅 message/notice/request/meta_event 四类事件，且重复 start 无副作用。"""
    # Arrange
    gateway, source, _ = _make_gateway()

    # Act
    gateway.start()
    gateway.start()

    # Assert
    assert [event_type for event_type, _ in source.subscribed] == [
        "message",
        "notice",
        "request",
        "meta_event",
    ]
    assert source.unsubscribed == []


def test_gateway_stop_unsubscribes_all_subscriptions() -> None:
    """stop 时必须退订全部订阅；重复 stop 为无操作，不产生重复退订。"""
    # Arrange
    gateway, source, _ = _make_gateway()
    gateway.start()

    # Act
    gateway.stop()
    gateway.stop()

    # Assert
    assert [event_type for event_type, _ in source.unsubscribed] == [
        "message",
        "notice",
        "request",
        "meta_event",
    ]


@pytest.mark.asyncio
async def test_gateway_forwards_message_events_to_legacy_pipeline() -> None:
    """群聊/私聊消息事件必须转发到 legacy 管线，未知 message_type 被忽略。"""
    # Arrange
    gateway, _, legacy = _make_gateway()
    group_event = {"post_type": "message", "message_type": "group", "message_id": 1}
    private_event = {"post_type": "message", "message_type": "private", "message_id": 2}
    unknown_event = {"post_type": "message", "message_type": "bogus"}

    # Act
    await gateway.handle(group_event)
    await gateway.handle(private_event)
    await gateway.handle(unknown_event)

    # Assert
    assert legacy.group_calls == [(group_event, False)]
    assert legacy.private_calls == [(private_event, False)]


@pytest.mark.asyncio
async def test_gateway_strips_internal_event_metadata() -> None:
    """_neobot_skip_ai_reply 转为 skip_ai_reply 参数并从事件中剥离，_local_conversation_name 进入 metadata。"""
    # Arrange
    gateway, _, legacy = _make_gateway()
    event = {
        "post_type": "message",
        "message_type": "private",
        "message_id": 3,
        "_neobot_skip_ai_reply": True,
        "_local_conversation_name": "闲聊",
    }

    # Act
    await gateway.handle(event)

    # Assert
    assert len(legacy.private_calls) == 1
    forwarded, skip_ai_reply = legacy.private_calls[0]
    assert skip_ai_reply is True
    assert "_neobot_skip_ai_reply" not in forwarded
    assert "_local_conversation_name" not in forwarded


@pytest.mark.asyncio
async def test_gateway_consumed_event_is_not_routed() -> None:
    """插件钩子消费事件后，gateway 不得继续路由到任何处理器。"""
    # Arrange
    legacy = _FakeLegacy()
    gateway, source, _ = _make_gateway(
        hook_bus=_FakeHookBus(consumed=True),
        legacy=legacy,
    )
    event = {"post_type": "message", "message_type": "group", "message_id": 4}

    # Act
    await gateway.handle(event)

    # Assert
    assert legacy.group_calls == []
    assert legacy.private_calls == []


@pytest.mark.asyncio
async def test_gateway_routes_notice_request_and_meta_events() -> None:
    """notice/request/meta_event 分别路由到对应处理器。"""
    # Arrange
    notice = _FakeHandler()
    request = _FakeHandler()
    lifecycle = _FakeHandler()
    gateway, _, _ = _make_gateway(notice=notice, request=request, lifecycle=lifecycle)

    # Act
    await gateway.handle({"post_type": "notice", "notice_type": "group_recall"})
    await gateway.handle({"post_type": "request", "request_type": "friend"})
    await gateway.handle({"post_type": "meta_event", "meta_event_type": "lifecycle"})

    # Assert
    assert len(notice.calls) == 1
    assert len(request.calls) == 1
    assert len(lifecycle.calls) == 1
