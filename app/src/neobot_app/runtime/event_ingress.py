from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.runtime.event_context import EventContext


class EventIngress:
    def __init__(
        self,
        *,
        event_source: Any,
        hook_bus: Any,
        router: Any,
        logger: Logger | None = None,
    ) -> None:
        self._event_source = event_source
        self._hook_bus = hook_bus
        self._router = router
        self._logger = logger or NullLogger()
        self._subscriptions: list[Any] = []
        self._started = False

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
        await self._router.route(ctx)
