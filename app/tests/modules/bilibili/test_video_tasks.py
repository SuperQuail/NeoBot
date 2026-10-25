"""B站视频后台解析：每群并发 3 与通知。"""

from __future__ import annotations

import asyncio
import json

import neobot_app.bilibili.video_tasks as video_tasks_module
from neobot_app.bilibili.video_tasks import MAX_NOTIFY_CHARS, BilibiliVideoTaskManager


class _FakeVideo:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def watch(self, identifier: str, *, max_chars: int, include_comments: int):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            return {"ok": True, "bvid": "BV1", "title": "视频", "transcript": "内容", "comments": []}
        finally:
            self.active -= 1


class _FakeHub:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, **kwargs):
        self.published.append(str(kwargs.get("content") or ""))
        return True


async def test_video_tasks_limit_three_per_flow_and_notify() -> None:
    video = _FakeVideo()
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(video_service=video, notification_hub=hub)

    results = [
        await manager.submit(flow_key="group:1", identifier=f"BV{i}", include_comments=3)
        for i in range(4)
    ]
    assert all(item["ok"] for item in results)
    for _ in range(40):
        if len(hub.published) >= 4:
            break
        await asyncio.sleep(0.02)

    assert video.max_active <= 3
    assert len(hub.published) == 4
    status = manager.get_pipeline_status("group:1")
    assert status["active"] == 0
    assert len(status["tasks"]) == 4


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("等待后台任务超时")


class _FailingVideo:
    async def watch(self, identifier: str, *, max_chars: int, include_comments: int):
        return {"ok": False, "error": "评论区已关闭"}


class _SlowVideo:
    async def watch(self, identifier: str, *, max_chars: int, include_comments: int):
        await asyncio.sleep(10)
        return {"ok": True}


class _LongTranscriptVideo:
    async def watch(self, identifier: str, *, max_chars: int, include_comments: int):
        return {
            "ok": True,
            "bvid": "BV1",
            "title": "标题",
            "transcript": "字" * 20000,
            "comments": [],
        }


async def test_failed_task_notifies_real_error() -> None:
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(
        video_service=_FailingVideo(), notification_hub=hub
    )

    await manager.submit(flow_key="group:1", identifier="BV1")
    await _wait_for(lambda: len(hub.published) == 1)

    payload = json.loads(hub.published[0].split("\n", 1)[1])
    assert payload["status"] == "failed"
    assert payload["error"] == "评论区已关闭"


async def test_cancelled_task_does_not_publish_failure() -> None:
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(
        video_service=_SlowVideo(), notification_hub=hub
    )

    await manager.submit(flow_key="group:1", identifier="BV1")
    await asyncio.sleep(0.02)  # 让后台任务真正跑起来，再模拟取消
    for task in list(manager._bg_tasks):
        task.cancel()
    await asyncio.sleep(0.1)

    assert hub.published == []
    assert manager.get_pipeline_status("group:1")["tasks"][0]["status"] == "cancelled"


async def test_long_transcript_notification_stays_valid_json() -> None:
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(
        video_service=_LongTranscriptVideo(), notification_hub=hub
    )

    await manager.submit(flow_key="group:1", identifier="BV1")
    await _wait_for(lambda: len(hub.published) == 1)

    payload_text = hub.published[0].split("\n", 1)[1]
    assert len(payload_text) <= MAX_NOTIFY_CHARS
    payload = json.loads(payload_text)  # 不硬切 JSON：截断后仍然可解析
    assert payload["bvid"] == "BV1"
    assert len(payload["transcript"]) < 20000


async def test_finished_tasks_are_pruned_by_count(monkeypatch) -> None:
    monkeypatch.setattr(video_tasks_module, "MAX_TASKS", 1)
    video = _FakeVideo()
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(video_service=video, notification_hub=hub)

    first = await manager.submit(flow_key="group:1", identifier="BV1")
    await _wait_for(lambda: len(hub.published) == 1)
    second = await manager.submit(flow_key="group:1", identifier="BV2")
    await _wait_for(lambda: len(hub.published) == 2)

    assert first["task_id"] not in manager._tasks
    assert [item["task_id"] for item in manager.get_pipeline_status("group:1")["tasks"]] == [
        second["task_id"]
    ]


async def test_finished_tasks_are_pruned_by_ttl(monkeypatch) -> None:
    monkeypatch.setattr(video_tasks_module, "TASK_TTL_SECONDS", 0.0)
    video = _FakeVideo()
    hub = _FakeHub()
    manager = BilibiliVideoTaskManager(video_service=video, notification_hub=hub)

    first = await manager.submit(flow_key="group:1", identifier="BV1")
    await _wait_for(lambda: len(hub.published) == 1)
    await manager.submit(flow_key="group:1", identifier="BV2")

    assert first["task_id"] not in manager._tasks
    assert manager.get_pipeline_status("group:1")["active"] == 1
