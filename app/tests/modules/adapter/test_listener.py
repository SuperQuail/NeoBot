"""ListenerManager（事件监听器管理器）的单元测试。

ListenerManager 是进程级单例，autouse fixture 在每个用例前后重置全局状态，
避免用例间互相污染；异常隔离与并发分发为覆盖重点。
"""

from __future__ import annotations

import asyncio

import pytest

from neobot_adapter.listener.manager import EventFilter, EventHandler, ListenerManager


@pytest.fixture(autouse=True)
def _reset_listener_manager() -> None:
    """每个用例前后重置 ListenerManager 单例的全局状态。"""
    manager = ListenerManager()
    manager.stop()
    manager.clear()
    manager._core = None
    yield
    manager.stop()
    manager.clear()


def _async_handler(records: list):
    """构造一个把事件 append 到 records 的异步处理器。"""

    async def handler(event: dict) -> None:
        records.append(event)

    return handler


@pytest.mark.asyncio
async def test_listener_dispatches_event_to_matching_async_handler() -> None:
    """注册的异步处理器必须收到过滤条件匹配的事件。"""
    manager = ListenerManager()
    seen: list[dict] = []
    manager.register(
        EventHandler(func=_async_handler(seen), filter=EventFilter(post_type="message"), is_async=True)
    )
    event = {"post_type": "message", "message_type": "private", "user_id": 1}

    await manager._dispatch_async(event)

    assert seen == [event]


@pytest.mark.xfail(reason="BUG-01 EventHandler.__post_init__ 包装了 func，unregister 按原函数比较永远不相等，注销必然失败", strict=False)
@pytest.mark.asyncio
async def test_listener_unregister_removes_handler() -> None:
    """unregister 后处理器必须不再接收事件，并返回 True 表示注销成功。"""
    manager = ListenerManager()
    seen: list[dict] = []
    handler_fn = _async_handler(seen)
    manager.register(EventHandler(func=handler_fn, filter=EventFilter(post_type="message"), is_async=True))
    event = {"post_type": "message", "message_type": "private", "user_id": 1}

    removed = manager.unregister(handler_fn)
    await manager._dispatch_async(event)

    assert removed is True
    assert seen == []


@pytest.mark.asyncio
async def test_listener_handlers_run_in_priority_order() -> None:
    """同一事件的多个处理器必须按优先级从高到低依次执行。"""
    manager = ListenerManager()
    order: list[str] = []

    async def low(event: dict) -> None:
        order.append("low")

    async def high(event: dict) -> None:
        order.append("high")

    manager.register(EventHandler(func=low, filter=EventFilter(post_type="message"), is_async=True, priority=0))
    manager.register(EventHandler(func=high, filter=EventFilter(post_type="message"), is_async=True, priority=100))

    await manager._dispatch_async({"post_type": "message"})

    assert order == ["high", "low"]


@pytest.mark.asyncio
async def test_listener_filter_filters_out_non_matching_events() -> None:
    """过滤器必须按 post_type/message_type 同时匹配，任一条件不满足则不分发。"""
    manager = ListenerManager()
    seen: list[dict] = []
    manager.register(
        EventHandler(
            func=_async_handler(seen),
            filter=EventFilter(post_type="message", message_type="private"),
            is_async=True,
        )
    )

    await manager._dispatch_async({"post_type": "message", "message_type": "group", "user_id": 1})
    await manager._dispatch_async({"post_type": "notice", "notice_type": "group_poke"})
    await manager._dispatch_async({"post_type": "message", "message_type": "private", "user_id": 2})

    assert len(seen) == 1
    assert seen[0]["user_id"] == 2


@pytest.mark.asyncio
async def test_listener_async_dispatch_isolates_handler_exception() -> None:
    """某个处理器抛异常时不得中断分发，其他处理器必须继续收到事件。"""
    manager = ListenerManager()
    seen: list[dict] = []

    async def boom(event: dict) -> None:
        raise RuntimeError("handler failure")

    manager.register(EventHandler(func=boom, filter=EventFilter(post_type="message"), is_async=True))
    manager.register(
        EventHandler(func=_async_handler(seen), filter=EventFilter(post_type="message"), is_async=True)
    )
    event = {"post_type": "message"}

    await manager._dispatch_async(event)

    assert seen == [event]


@pytest.mark.asyncio
async def test_listener_concurrent_dispatch_reaches_all_handlers() -> None:
    """并发分发两个事件时，所有已注册的处理器都必须收到全部事件。"""
    manager = ListenerManager()
    first: list[dict] = []
    second: list[dict] = []
    manager.register(
        EventHandler(func=_async_handler(first), filter=EventFilter(post_type="message"), is_async=True)
    )
    manager.register(
        EventHandler(func=_async_handler(second), filter=EventFilter(post_type="message"), is_async=True)
    )
    event_a = {"post_type": "message", "user_id": 1}
    event_b = {"post_type": "message", "user_id": 2}

    await asyncio.gather(manager._dispatch_async(event_a), manager._dispatch_async(event_b))

    assert len(first) == 2
    assert {item["user_id"] for item in first} == {1, 2}
    assert len(second) == 2
    assert {item["user_id"] for item in second} == {1, 2}
