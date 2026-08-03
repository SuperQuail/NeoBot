from __future__ import annotations

import asyncio

import pytest

from neobot_app.runtime.notifications import BackgroundNotificationHub


async def _publish(hub: BackgroundNotificationHub, conversation_id: str, content: str) -> None:
    await hub.publish(
        source="drawing",
        kind="drawing",
        conversation_id=conversation_id,
        content=content,
    )


@pytest.mark.asyncio
async def test_publish_drops_oldest_when_queue_full():
    hub = BackgroundNotificationHub()
    hub._queue_max_size = 2
    for i in range(3):
        await _publish(hub, "42", f"notice-{i}")

    key = "drawing:42"
    assert hub._queues[key].qsize() == 2

    first = await hub.poll(key)
    assert first is not None
    assert first.content == "notice-1"


@pytest.mark.asyncio
async def test_poll_drains_and_removes_empty_queue_key():
    hub = BackgroundNotificationHub()
    for i in range(3):
        await _publish(hub, "42", f"notice-{i}")

    key = "drawing:42"
    assert key in hub._queues
    for i in range(3):
        notification = await hub.poll(key)
        assert notification is not None
        assert notification.content == f"notice-{i}"

    assert key not in hub._queues
    assert await hub.poll(key) is None


@pytest.mark.asyncio
async def test_idle_queue_key_swept_after_ttl():
    hub = BackgroundNotificationHub()
    hub._queue_sweep_interval_seconds = 0.0
    await _publish(hub, "42", "stale")
    key = "drawing:42"
    assert key in hub._queues

    hub._queue_idle_ttl_seconds = 0.05
    await asyncio.sleep(0.1)
    await _publish(hub, "43", "fresh")

    assert key not in hub._queues
    assert "drawing:43" in hub._queues


@pytest.mark.asyncio
async def test_publish_drops_oldest_beyond_capacity_keeps_newest_three():
    """Arrange 队列上限 3，Act 连续 publish 5 条通知，Assert 队列只保留最新 3 条，
    轮询顺序为 notice-2/3/4，最早的 notice-0/1 被丢弃。"""
    hub = BackgroundNotificationHub()
    hub._queue_max_size = 3
    for i in range(5):
        await _publish(hub, "42", f"notice-{i}")

    key = "drawing:42"
    assert hub._queues[key].qsize() == 3
    contents = []
    for _ in range(3):
        notification = await hub.poll(key)
        assert notification is not None
        contents.append(notification.content)
    assert contents == ["notice-2", "notice-3", "notice-4"]


@pytest.mark.asyncio
async def test_idle_sweep_removes_only_stale_keys_keeps_fresh():
    """Arrange 一条超过 TTL 的过期 key 与一条刚活跃的 key，Act 触发一次清扫，
    Assert 只删除过期 key（含 _last_used），新鲜 key 及其通知原样保留。"""
    hub = BackgroundNotificationHub()
    hub._queue_sweep_interval_seconds = 0.0
    await _publish(hub, "42", "stale")
    stale_key = "drawing:42"

    hub._queue_idle_ttl_seconds = 0.05
    await asyncio.sleep(0.1)
    await _publish(hub, "43", "fresh")
    fresh_key = "drawing:43"
    await _publish(hub, "44", "trigger")

    assert stale_key not in hub._queues
    assert stale_key not in hub._last_used
    assert fresh_key in hub._queues
    assert hub._queues[fresh_key].qsize() == 1


@pytest.mark.asyncio
async def test_clear_then_publish_again_works():
    """Arrange 已入队一条通知并调用 clear，Act 重新 publish 同 key 新通知，
    Assert 旧队列/活跃标记清空后新通知可正常入队、状态可见并可被轮询。"""
    hub = BackgroundNotificationHub()
    await _publish(hub, "42", "old")
    key = "drawing:42"

    hub.clear()
    assert hub._queues == {}
    assert hub._last_used == {}

    await _publish(hub, "42", "new")
    assert key in hub._queues
    status = hub.get_pipeline_status(key)
    assert status["background_notifications_pending"] == 1
    notification = await hub.poll(key)
    assert notification is not None
    assert notification.content == "new"
