"""非对象 JSON 帧容错 + 接收器放弃停止后重建的回归测试。

对应两条 P1（证据见 dev-test/review/findings/V2.md）：

1. 非对象 JSON 帧（[]、不含 echo 的字符串、null、数字等）过去会被塞进消息队列，
   随后在 EventDispatcher.matches() 上抛 AttributeError 打死分发循环；而
   adapter.connected / 启动探针仍报「已连接」。
2. stop() 宽限耗尽后放弃旧接收线程，start() 只 logger.error 就返回（重建被静默
   拒绝），_connection_established 闩锁仍为真 -> wait_for_connection / 启动探针
   报「已连接、事件管线就绪」，实际没有任何监听。

这些用例必须在修复前的代码上失败：A 组旧代码下分发任务 done / handler 收不到
事件；B 组旧代码下 wait_for_connection() 返回 True 且 start() 不抛异常。
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from typing import Any, Callable

import pytest
import websockets

from neobot_adapter.onebot.adapter import OneBotAdapter
from neobot_adapter.onebot.receiver.core import AdapterCore
from neobot_app.runtime.connection_readiness import ConnectionReadinessProbe

MESSAGE_EVENT = json.dumps(
    {
        "post_type": "message",
        "message_type": "private",
        "user_id": 10001,
        "message": "hi",
        "raw_message": "hi",
    }
)

#: 旧代码下会拆连接（"echo" / 123 / ["echo"]）或打死分发循环（[] / "xx" / null / true）
NON_DICT_FRAMES = ["[]", '"xx"', '"echo"', "123", "null", "true", '["echo"]']


class _RecordingLogger:
    """记录 error / warning 的 Logger 替身，用于断言「异常退出可观测」。"""

    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, Any]]] = []
        self.warnings: list[tuple[str, dict[str, Any]]] = []

    def bind(self, **ctx: Any) -> "_RecordingLogger":
        return self

    def debug(self, msg: str, **kw: Any) -> None: ...

    def info(self, msg: str, **kw: Any) -> None: ...

    def warning(self, msg: str, **kw: Any) -> None:
        self.warnings.append((msg, kw))

    def error(self, msg: str, **kw: Any) -> None:
        self.errors.append((msg, kw))

    def exception(self, msg: str, **kw: Any) -> None:
        self.errors.append((msg, kw))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


# ── A. 非对象 JSON 帧 ────────────────────────────────────────────────


@pytest.mark.parametrize("frame", NON_DICT_FRAMES)
async def test_non_dict_frame_is_skipped_and_dispatch_stays_alive(frame: str) -> None:
    """非对象帧必须被跳过：连接不掉、事件照常分发、分发任务存活、队列只有 dict。"""
    port = _free_port()
    seen: list[dict[str, Any]] = []
    adapter = OneBotAdapter(host="127.0.0.1", port=port, max_queue_size=50)

    @adapter.on.message
    async def _handler(event: dict[str, Any]) -> None:
        seen.append(event)

    await adapter.start()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/onebot") as websocket:
            await websocket.send(frame)
            await asyncio.sleep(0.2)
            assert adapter.connected is True
            await websocket.send(MESSAGE_EVENT)
            assert await _wait_until(lambda: len(seen) == 1)
            assert adapter._dispatch_task is not None
            assert not adapter._dispatch_task.done()
            queued = list(adapter.core.message_queue.queue)
            assert all(isinstance(item, dict) for item in queued)
    finally:
        await adapter.stop()


async def test_dispatch_loop_survives_poisoned_queue_entry() -> None:
    """队列里出现非 dict 毒条目（绕过入口校验）时，分发循环必须继续工作。"""
    adapter = OneBotAdapter(host="127.0.0.1", port=_free_port(), max_queue_size=10)
    seen: list[dict[str, Any]] = []

    @adapter.on.message
    async def _handler(event: dict[str, Any]) -> None:
        seen.append(event)

    adapter.core.message_queue.put_nowait([])
    adapter.core.message_queue.put_nowait(
        {"post_type": "message", "message_type": "private", "user_id": 1, "message": "ok"}
    )
    task = asyncio.create_task(adapter._dispatch_loop())
    try:
        assert await _wait_until(lambda: len(seen) == 1)
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_dispatch_loop_survives_publish_failure() -> None:
    """分发层抛异常时只跳过该事件并告警，循环不得死亡。"""
    logger = _RecordingLogger()
    adapter = OneBotAdapter(
        host="127.0.0.1", port=_free_port(), logger=logger, max_queue_size=10
    )

    async def _boom(event: Any) -> None:
        raise RuntimeError("publish exploded")

    adapter._dispatcher.publish = _boom
    adapter.core.message_queue.put_nowait({"post_type": "message", "user_id": 1})
    task = asyncio.create_task(adapter._dispatch_loop())
    try:
        assert await _wait_until(
            lambda: any("事件分发失败" in msg for msg, _ in logger.errors)
        )
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_dispatch_task_abnormal_exit_is_reported() -> None:
    """分发任务异常退出必须被看护回调记录，而不是静默消失。"""
    logger = _RecordingLogger()
    adapter = OneBotAdapter(
        host="127.0.0.1", port=_free_port(), logger=logger, max_queue_size=10
    )

    def _broken_get_message(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("queue broken")

    adapter.core.get_message = _broken_get_message  # type: ignore[method-assign]
    await adapter.start()
    try:
        assert await _wait_until(
            lambda: adapter._dispatch_task is not None and adapter._dispatch_task.done()
        )
        assert await _wait_until(
            lambda: any(
                "分发循环异常退出" in msg and kw.get("error_type") == "RuntimeError"
                for msg, kw in logger.errors
            )
        )
    finally:
        await adapter.stop()


# ── B. 放弃停止后的重建与闩锁 ────────────────────────────────────────


async def test_abandoned_stop_is_identifiable_and_start_refuses() -> None:
    """stop() 放弃后：状态位可读、start() 显式失败、闩锁不再被当成「已连接」。"""
    core = AdapterCore()
    release = threading.Event()
    core.thread = threading.Thread(target=release.wait, args=(30,), daemon=True)
    core.thread.start()
    core._connection_established.set()  # 模拟「曾经连上过」的遗留闩锁

    try:
        # 修复前：只看闩锁 -> True（误报已连接）
        assert core.wait_for_connection(0.1) is False

        assert core.stop(timeout=0.2) is False
        assert core.abandoned is True

        old_thread = core.thread
        with pytest.raises(RuntimeError):
            core.start()
        assert core.thread is old_thread
        assert core.wait_for_connection(0.1) is False
    finally:
        release.set()


async def test_adapter_start_propagates_receiver_refusal_without_half_state() -> None:
    """Adapter 层：接收器拒绝重建时必须抛出，且不留下半启动的分发任务。"""
    adapter = OneBotAdapter(host="127.0.0.1", port=_free_port())
    core = adapter.core
    release = threading.Event()
    core.thread = threading.Thread(target=release.wait, args=(30,), daemon=True)
    core.thread.start()

    try:
        assert core.stop(timeout=0.2) is False
        assert adapter.receiver_abandoned is True

        with pytest.raises(RuntimeError):
            await adapter.start()

        assert adapter._dispatch_task is None
        assert adapter._stopping.is_set()
    finally:
        release.set()


async def test_normal_stop_start_cycle_still_rebuilds() -> None:
    """正常 stop→start（软重启/待机恢复）必须照常重建，不被「拒绝重建」误伤。

    回归护栏：stop() 会先置 _stop_event 再等线程，若 start() 只凭残留的
    _stop_event 就拒绝，健康的软重启会被误判成「旧线程卡死」，触发上层回滚
    甚至中断恢复流程。
    """
    port = _free_port()
    adapter = OneBotAdapter(host="127.0.0.1", port=port, max_queue_size=10)
    await adapter.start()
    first_thread = adapter.core.thread
    await adapter.stop()
    # 正常停止：接收线程已退出，核心不再持有线程引用（不会触发「拒绝重建」）。
    assert first_thread is not None and not first_thread.is_alive()
    assert adapter.core.thread is None

    await adapter.start()
    try:
        assert adapter.core.thread is not None
        assert adapter.core.thread is not first_thread
        assert adapter.core.thread.is_alive()
        assert adapter.core.abandoned is False

        async with websockets.connect(f"ws://127.0.0.1:{port}/onebot"):
            assert await _wait_until(lambda: adapter.connected is True)
            # 连接仍在线时探针必须报「已连接」（闩锁 + 活跃连接都成立）。
            probe = ConnectionReadinessProbe(adapter, wait_seconds=1.0)
            assert await _wait_until(
                lambda: probe.snapshot().connected, timeout=2.0
            )
            state = await probe.observe()
            assert state.connected is True
    finally:
        await adapter.stop()


async def test_readiness_probe_does_not_report_connected_after_abandoned_stop() -> None:
    """端到端：旧线程卡死 -> stop 放弃 -> 启动探针不得再报「已连接」。"""
    port = _free_port()
    adapter = OneBotAdapter(host="127.0.0.1", port=port)
    await adapter.start()
    core = adapter.core
    release = threading.Event()

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/onebot"):
            await asyncio.sleep(0.2)
            assert adapter.connected is True
        await asyncio.sleep(0.3)
        assert core._connection_established.is_set()

        # 卡死替身：占住接收线程的事件循环（真实场景见 _shutdown_loop 文档）
        core.loop.call_soon_threadsafe(release.wait, 30)
        await asyncio.sleep(0.2)

        assert core.stop(timeout=0.5) is False
        assert core.abandoned is True
        assert core.wait_for_connection(0.2) is False

        probe = ConnectionReadinessProbe(adapter, wait_seconds=0.2)
        state = await probe.observe()
        assert state.connected is False
        assert "已连接" not in state.startup_log()

        with pytest.raises(RuntimeError):
            core.start()
    finally:
        release.set()
        await asyncio.sleep(0.5)
        await adapter.stop()
