from __future__ import annotations

import asyncio
import inspect
import unittest
from typing import Any

from pydantic import BaseModel

from neobot_modloader.events import PluginEventBus


class FakeSubscription:
    def __init__(self) -> None:
        self.unsubscribed = False

    def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, dict[str, Any]]] = []

    def subscribe(self, event_type: Any, handler: Any, **filters: Any) -> FakeSubscription:
        self.calls.append((event_type, handler, filters))
        return FakeSubscription()


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.exceptions: list[str] = []

    def warning(self, msg: str, **kw: Any) -> None:
        self.warnings.append(msg)

    def exception(self, msg: str, **kw: Any) -> None:
        self.exceptions.append(msg)


class EventModel(BaseModel):
    raw_message: str


class PluginEventBusTest(unittest.IsolatedAsyncioTestCase):
    def test_message_registers_group_filters_and_subscription(self) -> None:
        adapter = FakeAdapter()
        subscriptions: list[Any] = []
        bus = PluginEventBus(adapter=adapter, record_subscription=subscriptions.append)

        @bus.message(group=True, priority=10)
        async def handler(event: dict[str, Any]) -> None:
            pass

        event_type, wrapped, filters = adapter.calls[0]
        self.assertEqual(event_type, "message")
        self.assertEqual(filters["message_type"], "group")
        self.assertEqual(filters["priority"], 10)
        self.assertEqual(len(subscriptions), 1)
        self.assertIs(wrapped.__wrapped__, handler)
        params = inspect.signature(wrapped).parameters
        self.assertEqual(next(iter(params.values())).name, "event")

    async def test_timeout_is_logged_and_swallowed(self) -> None:
        adapter = FakeAdapter()
        logger = FakeLogger()
        bus = PluginEventBus(adapter=adapter, logger=logger)

        @bus.message(timeout=0.01)
        async def handler(event: dict[str, Any]) -> None:
            await asyncio.sleep(1)

        wrapped = adapter.calls[0][1]
        await wrapped({})
        self.assertEqual(len(logger.warnings), 1)

    async def test_exception_is_logged_and_swallowed(self) -> None:
        adapter = FakeAdapter()
        logger = FakeLogger()
        bus = PluginEventBus(adapter=adapter, logger=logger)

        @bus.message()
        async def handler(event: EventModel) -> None:
            raise RuntimeError("boom")

        wrapped = adapter.calls[0][1]
        await wrapped(EventModel(raw_message="hi"))
        self.assertEqual(len(logger.exceptions), 1)
        self.assertIs(wrapped.__wrapped__, handler)

    async def test_message_text_matchers_compose_with_rule(self) -> None:
        adapter = FakeAdapter()
        bus = PluginEventBus(adapter=adapter)
        seen: list[dict[str, Any]] = []

        @bus.message(
            keywords=["菜单", "帮助"],
            contains=["NeoBot"],
            not_contains=["忽略"],
            regex=r"^NeoBot.*",
            rule=lambda event: event.get("allowed") is True,
        )
        async def handler(event: dict[str, Any]) -> None:
            seen.append(event)

        wrapped = adapter.calls[0][1]
        rule = adapter.calls[0][2]["rule"]
        matching = {"raw_message": "NeoBot 菜单", "allowed": True}
        self.assertTrue(await rule(matching))
        await wrapped(matching)
        self.assertEqual(seen, [matching])

        self.assertFalse(await rule({"raw_message": "NeoBot 菜单 忽略", "allowed": True}))
        self.assertFalse(await rule({"raw_message": "NeoBot 菜单", "allowed": False}))
        self.assertFalse(await rule({"raw_message": "菜单", "allowed": True}))
        self.assertFalse(await rule({"raw_message": "NeoBot 其他", "allowed": True}))

    async def test_message_matchers_support_segments(self) -> None:
        adapter = FakeAdapter()
        bus = PluginEventBus(adapter=adapter)

        @bus.message(contains="hello")
        async def handler(event: dict[str, Any]) -> None:
            pass

        rule = adapter.calls[0][2]["rule"]
        self.assertTrue(await rule({"message": [{"type": "text", "data": {"text": "he"}}, {"type": "image"}, {"type": "text", "data": {"text": "llo"}}]}))

    async def test_block_records_after_successful_handler(self) -> None:
        adapter = FakeAdapter()
        blocked: list[Any] = []
        bus = PluginEventBus(adapter=adapter, record_ai_reply_block=blocked.append)

        @bus.message(block=True)
        async def handler(event: dict[str, Any]) -> str:
            return "ok"

        event = {"message_id": 1, "raw_message": "hi"}
        result = await adapter.calls[0][1](event)
        self.assertEqual(result, "ok")
        self.assertEqual(blocked, [event])

    async def test_block_does_not_record_on_exception_or_timeout(self) -> None:
        adapter = FakeAdapter()
        logger = FakeLogger()
        blocked: list[Any] = []
        bus = PluginEventBus(adapter=adapter, logger=logger, record_ai_reply_block=blocked.append)

        @bus.message(block=True)
        async def boom(event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        @bus.message(block=True, timeout=0.01)
        async def slow(event: dict[str, Any]) -> None:
            await asyncio.sleep(1)

        await adapter.calls[0][1]({"message_id": 1})
        await adapter.calls[1][1]({"message_id": 2})
        self.assertEqual(blocked, [])
        self.assertEqual(len(logger.exceptions), 1)
        self.assertEqual(len(logger.warnings), 1)

    def test_group_and_private_are_mutually_exclusive(self) -> None:
        bus = PluginEventBus(adapter=FakeAdapter())
        with self.assertRaises(ValueError):
            bus.message(group=True, private=True)


if __name__ == "__main__":
    unittest.main()
