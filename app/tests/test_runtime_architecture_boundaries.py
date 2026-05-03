from __future__ import annotations

import unittest
from typing import Any

from neobot_app.runtime.event_context import EventContext
from neobot_app.runtime.event_ingress import EventIngress
from neobot_app.runtime.event_router import EventRouter
from neobot_app.runtime.message_pipeline import MessagePipeline


class FakeSubscription:
    def __init__(self, topic: str) -> None:
        self.topic = topic
        self.unsubscribed = False

    def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakeEventSource:
    def __init__(self) -> None:
        self.subscriptions: list[FakeSubscription] = []
        self.handlers: dict[str, Any] = {}

    def subscribe(self, topic: str, handler: Any) -> FakeSubscription:
        subscription = FakeSubscription(topic)
        self.subscriptions.append(subscription)
        self.handlers[topic] = handler
        return subscription


class FakeHookBus:
    def __init__(self) -> None:
        self.seen: list[EventContext] = []
        self.consume = False
        self.block_ai_reply = False
        self.raise_error = False

    async def dispatch(self, ctx: EventContext) -> None:
        self.seen.append(ctx)
        if self.raise_error:
            raise RuntimeError("hook failed")
        if self.block_ai_reply:
            ctx.block_ai_reply()
        if self.consume:
            ctx.consume()


class FakeRouter:
    def __init__(self) -> None:
        self.seen: list[EventContext] = []

    async def route(self, ctx: EventContext) -> None:
        self.seen.append(ctx)


class FakeLogger:
    def __init__(self) -> None:
        self.debugs: list[tuple[str, dict[str, Any]]] = []
        self.exceptions: list[str] = []
        self.infos: list[str] = []

    def debug(self, message: str, **kwargs: Any) -> None:
        self.debugs.append((message, kwargs))

    def exception(self, message: str, **kwargs: Any) -> None:
        self.exceptions.append(message)

    def info(self, message: str, **kwargs: Any) -> None:
        self.infos.append(message)


class FakeHandler:
    def __init__(self) -> None:
        self.seen: list[EventContext] = []

    async def handle(self, ctx: EventContext) -> None:
        self.seen.append(ctx)


class FakeLegacyMessagePipeline:
    def __init__(self) -> None:
        self.private_calls: list[tuple[dict[str, Any], bool]] = []
        self.group_calls: list[tuple[dict[str, Any], bool]] = []
        self.flushed = False

    async def handle_private_message_event(self, event: dict[str, Any], *, skip_ai_reply: bool = False) -> None:
        self.private_calls.append((event, skip_ai_reply))

    async def handle_group_message_event(self, event: dict[str, Any], *, skip_ai_reply: bool = False) -> None:
        self.group_calls.append((event, skip_ai_reply))

    async def flush_pending_summaries(self) -> None:
        self.flushed = True


class EventContextTest(unittest.TestCase):
    def test_context_exposes_public_flow_control_flags(self) -> None:
        ctx = EventContext(raw_event={"post_type": 123})

        ctx.block_ai_reply()
        ctx.consume()
        ctx.metadata["source"] = "test"

        self.assertEqual(ctx.post_type, "123")
        self.assertTrue(ctx.skip_ai_reply)
        self.assertTrue(ctx.consumed)
        self.assertEqual(ctx.metadata, {"source": "test"})


class EventIngressTest(unittest.IsolatedAsyncioTestCase):
    def make_ingress(
        self,
        *,
        hook_bus: FakeHookBus | None = None,
        router: FakeRouter | None = None,
        logger: FakeLogger | None = None,
    ) -> tuple[EventIngress, FakeEventSource, FakeHookBus, FakeRouter, FakeLogger]:
        source = FakeEventSource()
        hook_bus = hook_bus or FakeHookBus()
        router = router or FakeRouter()
        logger = logger or FakeLogger()
        ingress = EventIngress(
            event_source=source,
            hook_bus=hook_bus,
            router=router,
            logger=logger,
        )
        return ingress, source, hook_bus, router, logger

    def test_start_subscribes_only_canonical_post_types_and_stop_unsubscribes(self) -> None:
        ingress, source, _, _, logger = self.make_ingress()

        ingress.start()
        ingress.start()

        self.assertEqual([item.topic for item in source.subscriptions], ["message", "notice", "request", "meta_event"])
        self.assertEqual(set(source.handlers), {"message", "notice", "request", "meta_event"})
        self.assertEqual(logger.infos, ["事件入口已启动"])

        ingress.stop()

        self.assertTrue(all(item.unsubscribed for item in source.subscriptions))
        self.assertEqual(logger.infos, ["事件入口已启动", "事件入口已停止"])

    async def test_handle_runs_hooks_before_router_with_same_context(self) -> None:
        ingress, _, hook_bus, router, _ = self.make_ingress()
        raw_event = {"post_type": "message", "message_type": "group"}

        await ingress.handle(raw_event)

        self.assertEqual(len(hook_bus.seen), 1)
        self.assertEqual(len(router.seen), 1)
        self.assertIs(hook_bus.seen[0], router.seen[0])
        self.assertIs(router.seen[0].raw_event, raw_event)

    async def test_hook_consumed_event_short_circuits_router(self) -> None:
        hook_bus = FakeHookBus()
        hook_bus.consume = True
        ingress, _, _, router, logger = self.make_ingress(hook_bus=hook_bus)

        await ingress.handle({"post_type": "message", "message_type": "private"})

        self.assertEqual(router.seen, [])
        self.assertEqual(logger.debugs[0][0], "事件已被插件消费")

    async def test_skip_ai_reply_flag_is_propagated_to_router(self) -> None:
        hook_bus = FakeHookBus()
        hook_bus.block_ai_reply = True
        ingress, _, _, router, _ = self.make_ingress(hook_bus=hook_bus)

        await ingress.handle({"post_type": "message", "message_type": "group"})

        self.assertEqual(len(router.seen), 1)
        self.assertTrue(router.seen[0].skip_ai_reply)
        self.assertFalse(router.seen[0].consumed)

    async def test_hook_dispatch_failure_is_logged_and_router_still_runs(self) -> None:
        hook_bus = FakeHookBus()
        hook_bus.raise_error = True
        ingress, _, _, router, logger = self.make_ingress(hook_bus=hook_bus)

        await ingress.handle({"post_type": "notice", "notice_type": "poke"})

        self.assertEqual(len(router.seen), 1)
        self.assertEqual(len(logger.exceptions), 1)


class MessagePipelineFacadeTest(unittest.IsolatedAsyncioTestCase):
    async def test_delegates_private_messages_to_public_legacy_boundary(self) -> None:
        legacy = FakeLegacyMessagePipeline()
        pipeline = MessagePipeline(legacy_pipeline=legacy)
        event = {"post_type": "message", "message_type": "private"}
        ctx = EventContext(raw_event=event, skip_ai_reply=True)

        await pipeline.handle(ctx)

        self.assertEqual(legacy.private_calls, [(event, True)])
        self.assertEqual(legacy.group_calls, [])

    async def test_delegates_group_messages_to_public_legacy_boundary(self) -> None:
        legacy = FakeLegacyMessagePipeline()
        pipeline = MessagePipeline(legacy_pipeline=legacy)
        event = {"post_type": "message", "message_type": "group"}

        await pipeline.handle(EventContext(raw_event=event))

        self.assertEqual(legacy.group_calls, [(event, False)])
        self.assertEqual(legacy.private_calls, [])

    async def test_flush_pending_summaries_delegates_to_legacy_boundary(self) -> None:
        legacy = FakeLegacyMessagePipeline()
        pipeline = MessagePipeline(legacy_pipeline=legacy)

        await pipeline.flush_pending_summaries()

        self.assertTrue(legacy.flushed)


class EventRouterTest(unittest.IsolatedAsyncioTestCase):
    def make_router(self) -> tuple[EventRouter, dict[str, FakeHandler], FakeLogger]:
        handlers = {
            "message": FakeHandler(),
            "notice": FakeHandler(),
            "request": FakeHandler(),
            "meta_event": FakeHandler(),
        }
        logger = FakeLogger()
        router = EventRouter(
            message_pipeline=handlers["message"],
            notice_handler=handlers["notice"],
            request_handler=handlers["request"],
            lifecycle_handler=handlers["meta_event"],
            logger=logger,
        )
        return router, handlers, logger

    async def test_routes_each_canonical_post_type_to_one_handler(self) -> None:
        router, handlers, _ = self.make_router()

        for post_type in ("message", "notice", "request", "meta_event"):
            ctx = EventContext(raw_event={"post_type": post_type})
            await router.route(ctx)

        for post_type, handler in handlers.items():
            self.assertEqual(len(handler.seen), 1, post_type)
            self.assertEqual(handler.seen[0].post_type, post_type)

    async def test_unknown_post_type_is_logged_without_dispatching(self) -> None:
        router, handlers, logger = self.make_router()

        await router.route(EventContext(raw_event={"post_type": "unknown"}))

        self.assertTrue(all(not handler.seen for handler in handlers.values()))
        self.assertEqual(logger.debugs, [("未知事件类型", {"post_type": "unknown"})])


if __name__ == "__main__":
    unittest.main()
