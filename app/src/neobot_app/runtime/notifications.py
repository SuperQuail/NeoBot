"""Shared background notification delivery.

Background systems publish notifications to this hub.  The hub either starts a
background reply pipeline immediately or queues the notification for injection
into an already-active pipeline.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger


OnNotificationConsumed = Callable[["BackgroundNotification"], None | Awaitable[None]]


@dataclass(slots=True)
class BackgroundNotification:
    source: str
    pipeline_key: str
    kind: str
    conversation_id: str
    content: str
    manager_name: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    on_consumed: OnNotificationConsumed | None = None


class BackgroundNotificationHub:
    def __init__(
        self,
        *,
        orchestrator: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._logger = logger or NullLogger()
        self._queues: dict[str, asyncio.Queue[BackgroundNotification]] = {}

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def _get_callback_timeout_seconds(self) -> float:
        return 10.0

    async def publish(
        self,
        *,
        source: str,
        kind: str,
        conversation_id: str,
        content: str,
        manager_name: str | None = None,
        reasons: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        on_consumed: OnNotificationConsumed | None = None,
        on_polled: OnNotificationConsumed | None = None,
    ) -> bool:
        pipeline_key = f"{kind}:{conversation_id}"
        notification = BackgroundNotification(
            source=source,
            pipeline_key=pipeline_key,
            kind=kind,
            conversation_id=str(conversation_id),
            content=content,
            manager_name=manager_name or source,
            reasons=list(reasons or []),
            metadata=dict(metadata or {}),
            on_consumed=on_consumed or on_polled,
        )

        if await self._try_start_background_reply(notification):
            return True

        queue = self._queues.setdefault(pipeline_key, asyncio.Queue())
        await queue.put(notification)
        self._logger.info(
            "后台通知已入队",
            source=source,
            pipeline_key=pipeline_key,
            pending=queue.qsize(),
        )
        return False

    async def poll(
        self,
        pipeline_key: str,
        *,
        source: str | None = None,
    ) -> BackgroundNotification | None:
        queue = self._queues.get(pipeline_key)
        if queue is None or queue.empty():
            return None
        try:
            if source is None:
                notification = queue.get_nowait()
            else:
                notification = _pop_first_matching(queue, source)
                if notification is None:
                    return None
        except asyncio.QueueEmpty:
            return None

        await self._consume(notification)

        self._logger.info(
            "后台通知已被轮询取出",
            source=notification.source,
            pipeline_key=pipeline_key,
            notification_preview=notification.content[:120],
        )
        return notification

    def get_pipeline_status(self, pipeline_key: str) -> dict[str, Any]:
        queue = self._queues.get(pipeline_key)
        items = list(getattr(queue, "_queue", [])) if queue is not None else []
        by_source: dict[str, int] = {}
        for item in items:
            by_source[item.source] = by_source.get(item.source, 0) + 1
        return {
            "background_notifications_pending": len(items),
            "background_notifications_by_source": by_source,
        }

    def clear(self) -> None:
        self._queues.clear()

    async def _try_start_background_reply(self, notification: BackgroundNotification) -> bool:
        if self._orchestrator is None:
            return False

        active = getattr(self._orchestrator, "_active_pipelines", {})
        active_reply = active.get(notification.pipeline_key)
        pipeline_active = active_reply is not None and not active_reply.done()
        if pipeline_active:
            return False

        try:
            result = self._orchestrator.start_background_reply(
                kind=notification.kind,
                conversation_id=notification.conversation_id,
                content=notification.content,
                manager_name=notification.manager_name,
                reasons=notification.reasons or [f"{notification.source} notification"],
            )
        except Exception as exc:
            self._logger.warning(
                "后台通知启动回复管线失败",
                source=notification.source,
                pipeline_key=notification.pipeline_key,
                error=str(exc),
            )
            return False

        if result is None:
            return False

        await self._consume(notification)
        self._logger.info(
            "后台通知已启动回复管线",
            source=notification.source,
            pipeline_key=notification.pipeline_key,
        )
        return True

    async def _consume(self, notification: BackgroundNotification) -> None:
        if notification.on_consumed is None:
            return
        try:
            callback_result = notification.on_consumed(notification)
            if inspect.isawaitable(callback_result):
                await asyncio.wait_for(
                    callback_result,
                    timeout=self._get_callback_timeout_seconds(),
                )
        except asyncio.TimeoutError:
            self._logger.warning(
                "background notification consume callback timed out",
                source=notification.source,
                pipeline_key=notification.pipeline_key,
                timeout_seconds=self._get_callback_timeout_seconds(),
            )
        except Exception as exc:
            self._logger.warning(
                "background notification consume callback failed",
                source=notification.source,
                pipeline_key=notification.pipeline_key,
                error=str(exc),
            )


def _pop_first_matching(
    queue: asyncio.Queue[BackgroundNotification],
    source: str,
) -> BackgroundNotification | None:
    # asyncio.Queue intentionally has no selective pop API.  We only use this
    # for compatibility while older managers still expose source-specific poll
    # methods; the orchestrator normally polls without a source filter.
    items = getattr(queue, "_queue", None)
    if items is None:
        return None
    for item in list(items):
        if item.source == source:
            items.remove(item)
            return item
    return None
