from __future__ import annotations

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.runtime.event_context import EventContext


class OneBotRequestHandler:
    def __init__(self, *, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()

    async def handle(self, ctx: EventContext) -> None:
        event = ctx.raw_event
        request_type = event.get("request_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{request_type}" + (f".{sub_type}" if sub_type else "")
        details: list[str] = []
        for key in ("user_id", "group_id", "comment", "flag"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")
        info = " ".join(details)
        self._logger.info(f"收到请求[{label}] {info}".rstrip())
