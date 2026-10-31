"""把同步/工作线程日志投递到单 Bot 的事件循环，限制在途记录数量。"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from threading import Lock
from typing import Any


class AsyncLogDelivery:
    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._pending: deque[Any] = deque()
        self._lock = Lock()
        self._target: Callable[[Any], Awaitable[Any]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._scheduled = False
        self._generation = 0
        self._consuming: ContextVar[bool] = ContextVar("neobot_log_consuming", default=False)
        self.dropped = 0
        self.failed = 0

    def set_target(self, target: Callable[[Any], Awaitable[Any]] | None) -> None:
        with self._lock:
            old_task, old_loop = self._task, self._loop
            self._generation += 1
            self._target = target
            self._pending.clear()
            self._task = None
            self._scheduled = False
            self._loop = None
        if old_task is not None and old_loop is not None and not old_loop.is_closed():
            old_loop.call_soon_threadsafe(old_task.cancel)
        self.bind_loop()

    def bind_loop(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = loop
            self._schedule_locked()

    def submit(self, item: Any) -> None:
        # 消费者的故障诊断仍写文件/控制台，但不能反馈到同一个异步出口。
        if self._consuming.get():
            with self._lock:
                self.dropped += 1
            return
        self.bind_loop()
        with self._lock:
            if self._target is None:
                return
            if len(self._pending) >= self._capacity:
                self.dropped += 1
                return
            self._pending.append(item)
            self._schedule_locked()

    def _schedule_locked(self) -> None:
        loop = self._loop
        if not self._pending or self._scheduled or loop is None or loop.is_closed():
            return
        self._scheduled = True
        try:
            loop.call_soon_threadsafe(self._start, self._generation)
        except RuntimeError:
            self._scheduled = False

    def _start(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._task = asyncio.create_task(self._drain(generation), name="neobot-log-delivery")

    async def _drain(self, generation: int) -> None:
        cancelled = False
        processed = 0
        try:
            while True:
                with self._lock:
                    if generation != self._generation or not self._pending:
                        return
                    item = self._pending.popleft()
                    target = self._target
                if target is not None:
                    token = self._consuming.set(True)
                    try:
                        await target(item)
                    except Exception:
                        # 不在日志 sink 内再次打日志，避免接收方故障造成自激。
                        self.failed += 1
                    finally:
                        self._consuming.reset(token)
                processed += 1
                if processed % 64 == 0:
                    # async target 可能从不挂起；持续入队不能饿死心跳和关闭超时。
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            with self._lock:
                if generation == self._generation:
                    self._task = None
                    self._scheduled = False
                    if not cancelled:
                        self._schedule_locked()

    async def flush(self) -> None:
        self.bind_loop()
        while True:
            with self._lock:
                if not self._scheduled:
                    return
                task = self._task
            if task is None:
                await asyncio.sleep(0)
            else:
                await asyncio.shield(task)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"pending": len(self._pending), "dropped": self.dropped, "failed": self.failed}
