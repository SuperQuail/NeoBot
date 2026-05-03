from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.runtime.event_context import EventContext


class MessagePipeline:
    def __init__(
        self,
        *,
        legacy_pipeline: Any,
        logger: Logger | None = None,
    ) -> None:
        self._legacy = legacy_pipeline
        self._logger = logger or NullLogger()

    async def handle(self, ctx: EventContext) -> None:
        message_type = ctx.raw_event.get("message_type")
        if message_type == "private":
            await self._handle_private(ctx)
        elif message_type == "group":
            await self._handle_group(ctx)
        else:
            self._logger.debug("忽略未知消息类型", message_type=message_type)

    async def flush_pending_summaries(self) -> None:
        await self._legacy.flush_pending_summaries()

    async def _handle_private(self, ctx: EventContext) -> None:
        await self._legacy.handle_private_message_event(
            ctx.raw_event,
            skip_ai_reply=ctx.skip_ai_reply,
        )

    async def _handle_group(self, ctx: EventContext) -> None:
        await self._legacy.handle_group_message_event(
            ctx.raw_event,
            skip_ai_reply=ctx.skip_ai_reply,
        )
