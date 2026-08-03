"""EventGateway —— 统一的事件入口、路由与消息分发。

将原 EventIngress、EventRouter、MessagePipeline 三个薄层合并为约 120 行的
单一模块。真正的处理逻辑仍在 EventPipeline 中。
"""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.runtime.event_context import EventContext


class EventGateway:
    """接收原始事件，运行插件钩子，然后按 post_type 路由。

    取代三阶段管线::

        EventIngress → EventRouter → MessagePipeline

    合并后的类减少了内部交接，但对外行为一致：订阅 ``message`` /
    ``notice`` / ``request`` / ``meta_event``，将每个事件推入插件钩子总线，
    再分发到对应的处理器。
    """

    def __init__(
        self,
        *,
        event_source: Any,
        hook_bus: Any,
        legacy_pipeline: Any,
        notice_handler: object,
        request_handler: object,
        lifecycle_handler: object,
        logger: Logger | None = None,
    ) -> None:
        self._event_source = event_source
        self._hook_bus = hook_bus
        self._legacy = legacy_pipeline
        self._notice_handler = notice_handler
        self._request_handler = request_handler
        self._lifecycle_handler = lifecycle_handler
        self._logger = logger or NullLogger()
        self._subscriptions: list[Any] = []
        self._started = False

    # ── lifecycle ────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            return
        self._subscriptions = [
            self._event_source.subscribe("message", self.handle),
            self._event_source.subscribe("notice", self.handle),
            self._event_source.subscribe("request", self.handle),
            self._event_source.subscribe("meta_event", self.handle),
        ]
        self._started = True
        self._logger.info("事件入口已启动")

    def stop(self) -> None:
        if not self._started:
            return
        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()
        self._started = False
        self._logger.info("事件入口已停止")

    # ── main entry-point ─────────────────────────────────────

    async def handle(self, raw_event: dict[str, Any]) -> None:
        skip_ai_reply = bool(raw_event.get("_neobot_skip_ai_reply", False))
        clean_event = dict(raw_event)
        clean_event.pop("_neobot_skip_ai_reply", None)
        metadata: dict[str, Any] = {}
        local_conversation_name = clean_event.pop("_local_conversation_name", None)
        if local_conversation_name is not None:
            metadata["local_conversation_name"] = local_conversation_name

        ctx = EventContext(
            raw_event=clean_event,
            skip_ai_reply=skip_ai_reply,
            metadata=metadata,
        )

        # Plugin hook bus
        try:
            await self._hook_bus.dispatch(ctx)
        except Exception as exc:
            self._logger.exception(f"插件事件入口处理失败: {exc}")

        if ctx.consumed:
            self._logger.debug(
                "事件已被插件消费",
                post_type=ctx.post_type,
                message_type=raw_event.get("message_type"),
                notice_type=raw_event.get("notice_type"),
                request_type=raw_event.get("request_type"),
                meta_event_type=raw_event.get("meta_event_type"),
            )
            return

        await self._route(ctx)

    # ── routing (ex-EventRouter) ─────────────────────────────

    async def _route(self, ctx: EventContext) -> None:
        if ctx.post_type == "message":
            await self._handle_message(ctx)
        elif ctx.post_type == "notice":
            await self._notice_handler.handle(ctx)
        elif ctx.post_type == "request":
            await self._request_handler.handle(ctx)
        elif ctx.post_type == "meta_event":
            await self._lifecycle_handler.handle(ctx)
        else:
            self._logger.debug("未知事件类型", post_type=ctx.post_type)

    # ── message dispatch (ex-MessagePipeline) ────────────────

    async def _handle_message(self, ctx: EventContext) -> None:
        message_type = ctx.raw_event.get("message_type")
        if message_type == "private":
            await self._legacy.handle_private_message_event(
                ctx.raw_event,
                skip_ai_reply=ctx.skip_ai_reply,
            )
        elif message_type == "group":
            await self._legacy.handle_group_message_event(
                ctx.raw_event,
                skip_ai_reply=ctx.skip_ai_reply,
            )
        else:
            self._logger.debug("忽略未知消息类型", message_type=message_type)

    async def flush_pending_summaries(self) -> None:
        await self._legacy.flush_pending_summaries()
