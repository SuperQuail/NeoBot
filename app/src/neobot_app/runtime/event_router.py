from __future__ import annotations

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.runtime.event_context import EventContext


class EventRouter:
    def __init__(
        self,
        *,
        message_pipeline: object,
        notice_handler: object,
        request_handler: object,
        lifecycle_handler: object,
        logger: Logger | None = None,
    ) -> None:
        self._message_pipeline = message_pipeline
        self._notice_handler = notice_handler
        self._request_handler = request_handler
        self._lifecycle_handler = lifecycle_handler
        self._logger = logger or NullLogger()

    async def route(self, ctx: EventContext) -> None:
        if ctx.post_type == "message":
            await self._message_pipeline.handle(ctx)
        elif ctx.post_type == "notice":
            await self._notice_handler.handle(ctx)
        elif ctx.post_type == "request":
            await self._request_handler.handle(ctx)
        elif ctx.post_type == "meta_event":
            await self._lifecycle_handler.handle(ctx)
        else:
            self._logger.debug("未知事件类型", post_type=ctx.post_type)
