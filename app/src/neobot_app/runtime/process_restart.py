"""A durable, core-owned process restart request, independent of runtime generations."""

from __future__ import annotations

import asyncio
import threading


class ProcessRestartSignal:
    """One-shot request with thread-safe notification (not just a polled flag).

    A request made before a waiter exists is retained. Repeated requests coalesce;
    cancelling a waiter removes it without clearing the process's restart intent.
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
