from __future__ import annotations

import asyncio
import unittest
from typing import Any

from neobot_modloader.hooks import PluginHookBus


class FakeContext:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.exceptions: list[str] = []

    def warning(self, message: str, **kwargs: Any) -> None:
        self.warnings.append(message)

    def exception(self, message: str, **kwargs: Any) -> None:
        self.exceptions.append(message)


class PluginHookArchitectureContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_hooks_run_by_priority_and_only_when_filters_match(self) -> None:
        bus = PluginHookBus()
        seen: list[str] = []

        bus.subscribe(lambda event: seen.append("low"), post_type="message", message_type="group", priority=0)
        bus.subscribe(lambda event: seen.append("high"), post_type="message", message_type="group", priority=10)
        bus.subscribe(lambda event: seen.append("notice"), post_type="notice", priority=20)

        await bus.dispatch(FakeContext({"post_type": "message", "message_type": "group"}))

        self.assertEqual(seen, ["high", "low"])

    async def test_rule_false_skips_handler_without_consuming_event(self) -> None:
        bus = PluginHookBus()
        seen: list[str] = []

        async def rule(event: dict[str, Any]) -> bool:
            return event.get("allowed") is True

        bus.subscribe(lambda event: seen.append("handled"), post_type="message", rule=rule, block=True)
        ctx = FakeContext({"post_type": "message", "allowed": False})

        await bus.dispatch(ctx)

        self.assertEqual(seen, [])
        self.assertFalse(ctx.consumed)

    async def test_block_consumes_context_and_stops_later_hooks(self) -> None:
        bus = PluginHookBus()
        seen: list[str] = []

        bus.subscribe(lambda event: seen.append("first"), post_type="message", priority=10, block=True)
        bus.subscribe(lambda event: seen.append("second"), post_type="message", priority=0)
        ctx = FakeContext({"post_type": "message"})

        await bus.dispatch(ctx)

        self.assertTrue(ctx.consumed)
        self.assertEqual(seen, ["first"])

    async def test_block_ai_reply_records_intent_without_consuming_context(self) -> None:
        blocked: list[Any] = []
        bus = PluginHookBus(record_ai_reply_block=blocked.append)
        seen: list[str] = []
        event = {"post_type": "message", "message_id": 1}

        bus.subscribe(lambda payload: seen.append("first"), post_type="message", priority=10, block_ai_reply=True)
        bus.subscribe(lambda payload: seen.append("second"), post_type="message", priority=0)
        ctx = FakeContext(event)

        await bus.dispatch(ctx)

        self.assertFalse(ctx.consumed)
        self.assertTrue(ctx.skip_ai_reply)
        self.assertEqual(seen, ["first", "second"])
        self.assertEqual(blocked, [event])

    async def test_timeout_and_exception_are_logged_and_do_not_apply_block_flags(self) -> None:
        logger = FakeLogger()
        blocked: list[Any] = []
        bus = PluginHookBus(logger=logger, record_ai_reply_block=blocked.append)

        async def slow(event: dict[str, Any]) -> None:
            await asyncio.sleep(1)

        def boom(event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        bus.subscribe(slow, post_type="message", timeout=0.01, block=True, block_ai_reply=True)
        bus.subscribe(boom, post_type="message", block=True, block_ai_reply=True)
        ctx = FakeContext({"post_type": "message", "message_id": 1})

        await bus.dispatch(ctx)

        self.assertFalse(ctx.consumed)
        self.assertFalse(ctx.skip_ai_reply)
        self.assertEqual(blocked, [])
        self.assertEqual(len(logger.warnings), 1)
        self.assertEqual(len(logger.exceptions), 1)

    async def test_consumed_context_prevents_dispatching_remaining_hooks(self) -> None:
        bus = PluginHookBus()
        seen: list[str] = []

        def consume_before_return(event: dict[str, Any]) -> None:
            seen.append("first")

        bus.subscribe(consume_before_return, post_type="message", priority=10)
        bus.subscribe(lambda event: seen.append("second"), post_type="message", priority=0)
        ctx = FakeContext({"post_type": "message"})
        ctx.consume()

        await bus.dispatch(ctx)

        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
