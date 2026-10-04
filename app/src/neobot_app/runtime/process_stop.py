"""A durable, core-owned graceful-shutdown request, independent of runtime generations.

与 `ProcessRestartSignal` 同构，区别只在**意图**：一个是换一代进程，一个是让进程正常退出。
两者都要满足同一组约束，否则「停机」会在错误的时机丢失：

- **进程级持久**：请求先于等待者到达也要留住（面板可能比入口循环先起来）；
- **跨代际存活**：待机态、切换中、重建失败时收到的停机请求不能被丢掉，
  所以由核心持有，而不是挂在某一代 `Application` 上；
- **线程安全**：面板在自己的线程里调它，入口循环在事件循环里等它。
"""

from __future__ import annotations

import asyncio
import threading


class ProcessStopSignal:
    """One-shot graceful-shutdown request with thread-safe notification.

    请求可先于 waiter 到达并保留；重复请求合并（幂等）；取消 waiter 只影响等待，
    不会清掉进程的停机意图——否则一次超时取消就会让整次停机被遗忘。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requested = False
        self._waiters: set[asyncio.Future[None]] = set()

    @property
    def requested(self) -> bool:
        with self._lock:
            return self._requested

    def request(self) -> None:
        with self._lock:
            if self._requested:
                return
            self._requested = True
            waiters = tuple(self._waiters)
        for waiter in waiters:
            try:
                waiter.get_loop().call_soon_threadsafe(self._notify, waiter)
            except RuntimeError:
                # A closing event loop is no longer a consumer; intent stays set.
                pass

    @staticmethod
    def _notify(waiter: asyncio.Future[None]) -> None:
        if not waiter.done():
            waiter.set_result(None)

    async def wait(self) -> None:
        waiter = asyncio.get_running_loop().create_future()
        with self._lock:
            if self._requested:
                return
            self._waiters.add(waiter)
        try:
            await waiter
        finally:
            with self._lock:
                self._waiters.discard(waiter)
