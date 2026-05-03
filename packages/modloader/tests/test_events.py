from __future__ import annotations

import asyncio
import unittest
from typing import Any

from pydantic import BaseModel

from neobot_modloader.events import PluginEventBus
from neobot_modloader.hooks import PluginHookBus


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


class EventContext:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class PluginEventBusTest(unittest.IsolatedAsyncioTestCase):
    def make_bus(
        self,
        *,
        logger: FakeLogger | None = None,
        blocked: list[Any] | None = None,
        subscriptions: list[Any] | None = None,
    ) -> tuple[PluginEventBus, PluginHookBus]:
        hook_bus = PluginHookBus(logger=logger, record_ai_reply_block=blocked.append if blocked is not None else None)
        bus = PluginEventBus(
            hook_bus=hook_bus,
            logger=logger,
            record_subscription=subscriptions.append if subscriptions is not None else None,
        )
        return bus, hook_bus

    def test_message_registers_group_filters_and_subscription(self) -> None:
        subscriptions: list[Any] = []
        bus, hook_bus = self.make_bus(subscriptions=subscriptions)

        @bus.message(group=True, priority=10)
        async def handler(event: dict[str, Any]) -> None:
            pass

        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(len(hook_bus._hooks), 1)
        registration = hook_bus._hooks[0]
        self.assertEqual(registration.post_type, "message")
        self.assertEqual(registration.message_type, "group")
        self.assertEqual(registration.priority, 10)
        self.assertIs(registration.handler, handler)

    async def test_timeout_is_logged_and_swallowed(self) -> None:
        logger = FakeLogger()
        bus, hook_bus = self.make_bus(logger=logger)

        @bus.message(timeout=0.01)
        async def handler(event: dict[str, Any]) -> None:
            await asyncio.sleep(1)

        ctx = EventContext(raw_event={"post_type": "message", "raw_message": "hi"})
        await hook_bus.dispatch(ctx)
        self.assertEqual(len(logger.warnings), 1)
        self.assertFalse(ctx.consumed)

    async def test_exception_is_logged_and_swallowed(self) -> None:
        logger = FakeLogger()
        bus, hook_bus = self.make_bus(logger=logger)

        @bus.message()
        async def handler(event: EventModel) -> None:
            raise RuntimeError("boom")

        ctx = EventContext(raw_event={"post_type": "message", "raw_message": "hi"})
        await hook_bus.dispatch(ctx)
        self.assertEqual(len(logger.exceptions), 1)
        self.assertFalse(ctx.consumed)

    async def test_message_text_matchers_compose_with_rule(self) -> None:
        bus, hook_bus = self.make_bus()
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

        matching = {"post_type": "message", "raw_message": "NeoBot 菜单", "allowed": True}
        await hook_bus.dispatch(EventContext(raw_event=matching))
        self.assertEqual(seen, [matching])

        for event in (
            {"post_type": "message", "raw_message": "NeoBot 菜单 忽略", "allowed": True},
            {"post_type": "message", "raw_message": "NeoBot 菜单", "allowed": False},
            {"post_type": "message", "raw_message": "菜单", "allowed": True},
            {"post_type": "message", "raw_message": "NeoBot 其他", "allowed": True},
        ):
            await hook_bus.dispatch(EventContext(raw_event=event))
        self.assertEqual(seen, [matching])

    async def test_message_matchers_support_segments(self) -> None:
        bus, hook_bus = self.make_bus()
        seen: list[dict[str, Any]] = []

        @bus.message(contains="hello")
        async def handler(event: dict[str, Any]) -> None:
            seen.append(event)

        event = {
            "post_type": "message",
            "message": [
                {"type": "text", "data": {"text": "he"}},
                {"type": "image"},
                {"type": "text", "data": {"text": "llo"}},
            ],
        }
        await hook_bus.dispatch(EventContext(raw_event=event))
        self.assertEqual(seen, [event])

    async def test_block_consumes_event_and_stops_later_handlers(self) -> None:
        bus, hook_bus = self.make_bus()
        seen: list[str] = []

        @bus.message(priority=10, block=True)
        async def first(event: dict[str, Any]) -> None:
            seen.append("first")

        @bus.message(priority=0)
        async def second(event: dict[str, Any]) -> None:
            seen.append("second")

        ctx = EventContext(raw_event={"post_type": "message", "raw_message": "hi"})
        await hook_bus.dispatch(ctx)
        self.assertTrue(ctx.consumed)
        self.assertEqual(seen, ["first"])

    async def test_block_ai_reply_marks_context_but_continues(self) -> None:
        blocked: list[Any] = []
        bus, hook_bus = self.make_bus(blocked=blocked)
        seen: list[str] = []

        @bus.message(priority=10, block_ai_reply=True)
        async def first(event: dict[str, Any]) -> None:
            seen.append("first")

        @bus.message(priority=0)
        async def second(event: dict[str, Any]) -> None:
            seen.append("second")

        event = {"post_type": "message", "message_id": 1, "raw_message": "hi"}
        ctx = EventContext(raw_event=event)
        await hook_bus.dispatch(ctx)
        self.assertFalse(ctx.consumed)
        self.assertTrue(ctx.skip_ai_reply)
        self.assertEqual(seen, ["first", "second"])
        self.assertEqual(blocked, [event])

    async def test_block_flags_do_not_apply_on_exception_or_timeout(self) -> None:
        logger = FakeLogger()
        blocked: list[Any] = []
        bus, hook_bus = self.make_bus(logger=logger, blocked=blocked)

        @bus.message(block=True, block_ai_reply=True)
        async def boom(event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        @bus.message(block=True, block_ai_reply=True, timeout=0.01)
        async def slow(event: dict[str, Any]) -> None:
            await asyncio.sleep(1)

        ctx = EventContext(raw_event={"post_type": "message", "message_id": 1})
        await hook_bus.dispatch(ctx)
        self.assertFalse(ctx.consumed)
        self.assertFalse(ctx.skip_ai_reply)
        self.assertEqual(blocked, [])
        self.assertEqual(len(logger.exceptions), 1)
        self.assertEqual(len(logger.warnings), 1)

    def test_group_and_private_are_mutually_exclusive(self) -> None:
        bus, _ = self.make_bus()
        with self.assertRaises(ValueError):
            bus.message(group=True, private=True)


if __name__ == "__main__":
    unittest.main()
