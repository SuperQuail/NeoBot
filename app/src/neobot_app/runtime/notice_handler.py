from __future__ import annotations

from typing import Any

from neobot_app.runtime.event_context import EventContext


class NoticeHandler:
    def __init__(self, *, legacy_pipeline: Any) -> None:
        self._legacy = legacy_pipeline

    async def handle(self, ctx: EventContext) -> None:
        await self._legacy._handle_notice(ctx.raw_event)
