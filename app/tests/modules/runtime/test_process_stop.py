"""`ProcessStopSignal` 的行为：请求幂等、可先于等待者到达、取消等待不清意图。"""

from __future__ import annotations

import asyncio
import threading

from neobot_app.runtime.process_stop import ProcessStopSignal


async def test_request_before_waiter_is_retained() -> None:
    """面板可能比入口循环先收到请求：之后才来等的人必须立刻返回。"""
    signal = ProcessStopSignal()
    signal.request()
    assert signal.requested is True
    # 已经在等之前就置位：wait() 直接返回，不能挂住
    await asyncio.wait_for(signal.wait(), timeout=0.5)


async def test_waiter_is_woken_by_request() -> None:
    signal = ProcessStopSignal()
    assert signal.requested is False
    waiter = asyncio.create_task(signal.wait())
    await asyncio.sleep(0.01)
    assert not waiter.done()
    signal.request()
    await asyncio.wait_for(waiter, timeout=0.5)
    assert signal.requested is True


async def test_repeated_requests_are_idempotent() -> None:
    signal = ProcessStopSignal()
    signal.request()
    signal.request()
    signal.request()
    assert signal.requested is True


async def test_cancelling_waiter_keeps_the_intent() -> None:
    """取消等待（例如外层观察窗口到点）不能把停机意图一起丢掉。"""
    signal = ProcessStopSignal()
    waiter = asyncio.create_task(signal.wait())
    await asyncio.sleep(0.01)
    waiter.cancel()
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    # 意图没被请求过，仍是 False
    assert signal.requested is False
    # 之后来的请求照样生效，且新 waiter 能被叫醒
    again = asyncio.create_task(signal.wait())
    await asyncio.sleep(0.01)
    signal.request()
    await asyncio.wait_for(again, timeout=0.5)
    assert signal.requested is True


async def test_request_from_another_thread_wakes_the_waiter() -> None:
    """面板在自己的线程里调 request()，事件循环里的 waiter 要被叫醒。"""
    signal = ProcessStopSignal()
    waiter = asyncio.create_task(signal.wait())
    await asyncio.sleep(0.01)
    thread = threading.Thread(target=signal.request)
    thread.start()
    thread.join(timeout=2)
    await asyncio.wait_for(waiter, timeout=1.0)
    assert signal.requested is True
