"""通知被消费前发生取消时不得丢失。

poll() 先把通知从队列取出、再 await _consume(notification)（消费回调通常负责
写「已通知」落盘标记）。若在此期间被取消，通知直接消失且标记未写——之后管理
器还会重复投递。修复后取消时会把通知放回队列。
"""

from __future__ import annotations

import asyncio

from neobot_app.runtime.notifications import BackgroundNotificationHub


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **kw) -> None:
        self.warnings.append(message)

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        pass

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


def _hub() -> BackgroundNotificationHub:
    return BackgroundNotificationHub(logger=_Logger())


def _notification(consumed: list[str], *, block: asyncio.Event | None = None):
    async def _on_consumed(notification) -> None:
        if block is not None:
            await block.wait()
        consumed.append(notification.content)

    return _hub_notification(_on_consumed)


def _hub_notification(on_consumed):
    from neobot_app.runtime.notifications import BackgroundNotification

    return BackgroundNotification(
        source="drawing",
        pipeline_key="group:1",
        kind="group",
        conversation_id="1",
        content="画好了",
        manager_name="drawing",
        on_consumed=on_consumed,
    )


async def test_cancelled_consume_requeues_notification() -> None:
    hub = _hub()
    consumed: list[str] = []
    release = asyncio.Event()
    notification = _notification(consumed, block=release)
    hub._queues["group:1"] = asyncio.Queue()
    hub._queues["group:1"].put_nowait(notification)

    task = asyncio.create_task(hub.poll("group:1"))
    await asyncio.sleep(0)  # 让 poll 进入 _consume 并阻塞
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # 未完成消费 → 通知必须回到队列，不能丢
    assert consumed == []
    queue = hub._queues.get("group:1")
    assert queue is not None and queue.qsize() == 1


async def test_successful_consume_removes_notification() -> None:
    hub = _hub()
    consumed: list[str] = []
    hub._queues["group:1"] = asyncio.Queue()
    hub._queues["group:1"].put_nowait(_notification(consumed))

    result = await hub.poll("group:1")

    assert result is not None
    assert consumed == ["画好了"]
    assert hub._queues.get("group:1") is None  # 空队列被回收


async def test_consume_without_callback_drops_notification() -> None:
    """没有消费回调时行为不变：取出即完成。"""
    hub = _hub()
    hub._queues["group:1"] = asyncio.Queue()
    hub._queues["group:1"].put_nowait(_hub_notification(None))

    result = await hub.poll("group:1")

    assert result is not None
