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

# ── fix(2) D4：通知全量入管道（F14）───────────────────────────────


class _RecordingOrchestrator:
    """只记录 record_notification 调用的假编排器。"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def record_notification(self, *, kind, conversation_id, source, content) -> bool:
        self.records.append(
            {
                "kind": kind,
                "conversation_id": conversation_id,
                "source": source,
                "content": content,
            }
        )
        return True

    def is_pipeline_key_active(self, pipeline_key: str) -> bool:
        return False

    def start_background_reply(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_publish_mirrors_notification_into_message_queue():
    """任意 source 的通知在既有投递之外，必须同时写进对应会话的消息队列。"""
    orchestrator = _RecordingOrchestrator()
    hub = BackgroundNotificationHub(orchestrator=orchestrator)

    await hub.publish(
        source="balance_checker",
        kind="private",
        conversation_id="20001",
        content="余额不足",
    )

    assert orchestrator.records == [
        {
            "kind": "private",
            "conversation_id": "20001",
            "source": "balance_checker",
            "content": "余额不足",
        }
    ]


@pytest.mark.asyncio
async def test_publish_mirrors_before_starting_background_reply():
    """起管线路径也必须镜像：后启动的管线会 clone 队列，镜像晚一步就会漏。"""
    orchestrator = _RecordingOrchestrator()

    class _StartingOrchestrator:
        def __init__(self, inner) -> None:
            self._inner = inner
            self.started = 0

        def record_notification(self, **kwargs) -> bool:
            return self._inner.record_notification(**kwargs)

        def is_pipeline_key_active(self, pipeline_key: str) -> bool:
            return False

        def start_background_reply(self, **kwargs):
            self.started += 1
            assert self._inner.records, "通知必须在启动管线之前就写进消息队列"
            return object()

    hub = BackgroundNotificationHub()
    hub.set_orchestrator(_StartingOrchestrator(orchestrator))

    started = await hub.publish(
        source="drawing",
        kind="group",
        conversation_id="888888",
        content="绘图完成",
    )

    assert started is True
    assert len(orchestrator.records) == 1


@pytest.mark.asyncio
async def test_mirror_failure_does_not_break_delivery():
    """队列侧写失败绝不能影响通知的既有投递。"""

    class _BrokenOrchestrator:
        def record_notification(self, **kwargs) -> bool:
            raise RuntimeError("queue boom")

        def is_pipeline_key_active(self, pipeline_key: str) -> bool:
            return False

        def start_background_reply(self, **kwargs):
            return None

    hub = BackgroundNotificationHub(orchestrator=_BrokenOrchestrator())
    await hub.publish(
        source="scheduled_task", kind="group", conversation_id="1", content="提醒"
    )

    assert hub._queues["group:1"].qsize() == 1


@pytest.mark.asyncio
async def test_no_orchestrator_means_no_mirror_and_no_error():
    hub = BackgroundNotificationHub()
    await hub.publish(source="drawing", kind="group", conversation_id="1", content="x")
    assert hub._queues["group:1"].qsize() == 1

