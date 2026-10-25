"""插件生命周期：停轮询要等任务真正结束，shutdown 负责关掉 HTTP 连接。

这些用例守的是两个线上隐患：
1. stop_polling 取消任务后直接返回，modloader 紧接着 close_databases()，
   任务还活着就会在已关闭的引擎上读写；
2. 关停流程里的 CancelledError 被吃掉，导致关停/重载信号传不出去。
"""

from __future__ import annotations

import asyncio

import pytest
import streaming_parser
from streaming_parser import PluginState


class TestStopPolling:
    async def test_task_that_ignores_stop_is_cancelled_and_awaited(self, monkeypatch):
        state = PluginState()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def stubborn() -> None:
            started.set()
            try:
                await asyncio.sleep(30)  # 不听 stop 事件，模拟卡在长请求里
            finally:
                finished.set()

        task = asyncio.create_task(stubborn())
        state._task = task
        await started.wait()
        monkeypatch.setattr(streaming_parser, 'STOP_TIMEOUT', 0.05)

        await state.stop_polling()

        assert finished.is_set(), 'stop_polling 返回时任务必须已经收尾'
        assert task.done()
        assert state._task is None

    async def test_cooperative_task_finishes_without_cancel(self):
        state = PluginState()

        async def cooperative() -> None:
            await state._stop.wait()

        task = asyncio.create_task(cooperative())
        state._task = task
        await asyncio.sleep(0)

        await state.stop_polling()

        assert task.done()
        assert not task.cancelled()

    async def test_no_task_is_noop(self):
        state = PluginState()
        await state.stop_polling()
        assert state._task is None

    async def test_outer_cancellation_is_not_swallowed(self, monkeypatch):
        state = PluginState()
        state._task = asyncio.create_task(asyncio.sleep(30))
        monkeypatch.setattr(streaming_parser, 'STOP_TIMEOUT', 5.0)

        async def shutdown() -> None:
            await state.stop_polling()

        outer = asyncio.create_task(shutdown())
        await asyncio.sleep(0.01)
        outer.cancel()

        with pytest.raises(asyncio.CancelledError):
            await outer


class Holder:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class TestAclose:
    async def test_closes_client_and_assets(self):
        state = PluginState()
        client, assets = Holder(), Holder()
        state.client = client
        state.assets = assets

        await state.aclose()

        assert (client.closed, assets.closed) == (1, 1)

    async def test_missing_or_unloaded_holders_are_skipped(self):
        state = PluginState()
        state.client = object()  # 没有 aclose
        state.assets = None

        await state.aclose()  # 不抛异常
