"""共享的后台通知投递。

后台系统将通知发布到该中枢。中枢要么立即启动后台回复管线，
要么将通知排队以注入到已活跃的管线中。
"""

from __future__ import annotations

import asyncio
import inspect
import time
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
        self._last_used: dict[str, float] = {}
        self._last_sweep = 0.0
        self._queue_max_size = 100
        self._queue_idle_ttl_seconds = 1800.0
        self._queue_sweep_interval_seconds = 300.0

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

        queue = self._queues.get(pipeline_key)
        queue_size_before = queue.qsize() if queue is not None else 0
        self._logger.debug(
            "hub.publish() 入口",
            source=source,
            pipeline_key=pipeline_key,
            queue_size_before=queue_size_before,
        )

        if await self._try_start_background_reply(notification):
            self._logger.info(
                "hub.publish() 已启动新管线",
                source=source,
                pipeline_key=pipeline_key,
            )
            return True

        queue = self._queues.get(pipeline_key)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._queue_max_size)
            self._queues[pipeline_key] = queue
        self._last_used[pipeline_key] = time.monotonic()
        if queue.full():
            try:
                dropped = queue.get_nowait()
                self._logger.warning(
                    "hub.publish() 通知队列已满，丢弃最旧通知",
                    source=source,
                    pipeline_key=pipeline_key,
                    dropped_source=dropped.source,
                )
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(notification)
        self._logger.info(
            "hub.publish() 通知已入队",
            source=source,
            pipeline_key=pipeline_key,
            pending=queue.qsize(),
        )
        self._sweep_idle_queues()
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

        try:
            await self._consume(notification)
        except asyncio.CancelledError:
            # 取消发生在消费回调（例如「已通知」落盘标记）完成之前：直接丢弃会
            # 让这条通知消失，管理器的状态没更新还可能稍后重复投递，所以放回队列。
            self._requeue(pipeline_key, notification)
            raise

        self._last_used[pipeline_key] = time.monotonic()
        self._logger.info(
            "hub.poll() 取出通知",
            source=notification.source,
            pipeline_key=pipeline_key,
            notification_preview=notification.content[:120],
            remaining_in_queue=queue.qsize(),
        )
        if queue.empty() and not getattr(queue, "_getters", None):
            self._queues.pop(pipeline_key, None)
            self._last_used.pop(pipeline_key, None)
        return notification

    def _sweep_idle_queues(self) -> None:
        """惰性清理长期无人轮询的通知队列，防止 key 无限增长。"""
        now = time.monotonic()
        if now - self._last_sweep < self._queue_sweep_interval_seconds:
            return
        self._last_sweep = now
        idle_keys = [
            key
            for key, last_used in self._last_used.items()
            if now - last_used > self._queue_idle_ttl_seconds
        ]
        for key in idle_keys:
            self._queues.pop(key, None)
            self._last_used.pop(key, None)
            self._logger.debug(
                "hub 清理空闲通知队列",
                pipeline_key=key,
            )

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
        self._last_used.clear()

    async def _try_start_background_reply(self, notification: BackgroundNotification) -> bool:
        if self._orchestrator is None:
            self._logger.debug(
                "_try_start_background_reply: orchestrator 为空"
            )
            return False

        if self._orchestrator.is_pipeline_key_active(notification.pipeline_key):
            self._logger.info(
                "_try_start_background_reply: 管线已活跃，跳过启动",
                pipeline_key=notification.pipeline_key,
            )
            return False

        self._logger.info(
            "_try_start_background_reply: 尝试启动新管线",
            source=notification.source,
            pipeline_key=notification.pipeline_key,
        )
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
            self._logger.info(
                "_try_start_background_reply: start_background_reply 返回 None",
                pipeline_key=notification.pipeline_key,
                source=notification.source,
            )
            return False

        await self._consume(notification)
        self._logger.info(
            "后台通知已启动回复管线",
            source=notification.source,
            pipeline_key=notification.pipeline_key,
        )
        return True

    def _requeue(
        self, pipeline_key: str, notification: BackgroundNotification
    ) -> None:
        """把通知放回队列（消费被取消时使用），沿用 publish 的有界策略。"""
        queue = self._queues.get(pipeline_key)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._queue_max_size)
            self._queues[pipeline_key] = queue
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(notification)
        except asyncio.QueueFull:
            self._logger.warning(
                "后台通知重新入队失败，通知已丢弃",
                source=notification.source,
                pipeline_key=pipeline_key,
            )

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
                "后台通知消费回调超时",
                source=notification.source,
                pipeline_key=notification.pipeline_key,
                timeout_seconds=self._get_callback_timeout_seconds(),
            )
        except Exception as exc:
            self._logger.warning(
                "后台通知消费回调失败",
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
