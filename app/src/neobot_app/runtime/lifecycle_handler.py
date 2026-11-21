from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.runtime.event_context import EventContext


class LifecycleHandler:
    def __init__(
        self,
        *,
        logger: Logger | None = None,
        on_connect: Callable[[], Any] | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._on_connect = on_connect

    async def handle(self, ctx: EventContext) -> None:
        event = ctx.raw_event
        meta_event_type = event.get("meta_event_type", "未知")
        if meta_event_type == "heartbeat":
            status = event.get("status")
            if isinstance(status, dict) and (
                status.get("online") is False or status.get("good") is False
            ):
                self._logger.warning(f"心跳状态异常: {status}")
            return

        sub_type = event.get("sub_type", "")
        if meta_event_type == "lifecycle" and sub_type == "connect" and self._on_connect is not None:
            # 连接后的身份判定要走 API，放后台任务，绝不阻塞事件分发
            asyncio.create_task(self._trigger_on_connect())

        label = f"{meta_event_type}" + (f".{sub_type}" if sub_type else "")
        details: list[str] = []
        for key in ("interval", "status", "time", "self_id"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")
        info = " ".join(details)
        self._logger.info(f"收到元事件[{label}] {info}".rstrip())

    async def _trigger_on_connect(self) -> None:
        try:
            result = self._on_connect()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "连接后处理失败",
                error_type=type(exc).__name__,
                error=str(exc),
            )
