"""BackgroundDrawingManager 后台任务注册、shutdown 取消、重试与状态机测试。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.manager import BackgroundDrawingManager
from neobot_app.drawing.tasks import DrawTask


class _FakeHub:
    """假通知中心：publish 返回可配置的 started，记录调用。"""

    def __init__(self, started: bool = False) -> None:
        self.started = started
        self.published: list[dict] = []
        self.orchestrator = None

    def set_orchestrator(self, orchestrator) -> None:
        self.orchestrator = orchestrator

    async def publish(self, **kwargs) -> bool:
        self.published.append(kwargs)
        return self.started

    async def poll(self, pipeline_key, source=None):
        return None

    def get_pipeline_status(self, pipeline_key):
        return {"background_notifications_by_source": {}}


class _FakeImageService:
    """可控假绘图服务：可阻塞、可抛错，返回固定记录。"""

    def __init__(self, *, fail: Exception | None = None, block: bool = False) -> None:
        self.fail = fail
        self.block = block
        self.release = asyncio.Event()
        self.calls: list[dict] = []

    async def generate_image(self, **kwargs):
        self.calls.append(kwargs)
        if self.block:
            await self.release.wait()
        if self.fail is not None:
            raise self.fail
        return SimpleNamespace(
            image_id="img_test_1",
            source="tmp",
            file_path="img_test_1.png",
            prompt=kwargs.get("prompt"),
            description=None,
            mime_type="image/png",
            original_width=4,
            original_height=4,
        )


def _make_manager(
    *, service=None, hub=None, **overrides
) -> BackgroundDrawingManager:
    config = DrawServiceConfig(
        draw_startup_grace_seconds=0.01,
        draw_notification_retry_seconds=30,
        **overrides,
    )
    return BackgroundDrawingManager(
        image_service=service, config=config, notification_hub=hub
    )


async def _slow_noop() -> None:
    await asyncio.sleep(0.05)


def _submit_kwargs(**overrides) -> dict:
    kwargs = {
        "pipeline_key": "group:1",
        "conversation_kind": "group",
        "conversation_id": "1",
        "prompt": "画一只猫",
    }
    kwargs.update(overrides)
    return kwargs


async def test_spawn_bg_task_registers_and_discards_on_done() -> None:
    """_spawn_bg_task 注册的任务在完成回调后必须从 _bg_tasks 中移除。"""
    manager = _make_manager(service=_FakeImageService())

    task = manager._spawn_bg_task(_slow_noop())
    assert task in manager._bg_tasks

    await task
    await asyncio.sleep(0)
    assert manager._bg_tasks == set()


async def test_concurrent_spawn_registers_both_tasks() -> None:
    """并发注册两个后台任务必须互不干扰，完成后都被 discard。"""
    manager = _make_manager(service=_FakeImageService())

    async def _spawn() -> asyncio.Task:
        task = manager._spawn_bg_task(_slow_noop())
        await asyncio.sleep(0)
        return task

    t1, t2 = await asyncio.gather(_spawn(), _spawn())
    assert len(manager._bg_tasks) == 2

    await asyncio.gather(t1, t2)
    await asyncio.sleep(0)
    assert manager._bg_tasks == set()


async def test_shutdown_cancels_running_task() -> None:
    """shutdown() 必须取消正在运行（阻塞中）的绘图任务。"""
    service = _FakeImageService(block=True)
    manager = _make_manager(service=service)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["status"] == "drawing"
    bg = next(iter(manager._bg_tasks))
    assert not bg.done()

    await manager.shutdown()
    assert bg.cancelled()
    assert manager._bg_tasks == set()


async def test_retry_notification_task_cancelled_by_shutdown() -> None:
    """通知未启动管线而派生的重试任务必须随 shutdown 一并取消。"""
    hub = _FakeHub(started=False)
    manager = _make_manager(service=_FakeImageService(), hub=hub)
    task = DrawTask(
        task_id="draw_retry_1",
        pipeline_key="group:1",
        conversation_kind="group",
        conversation_id="1",
        prompt="p",
        status="completed",
        image_id="img_1",
        record_payload={},
    )

    await manager._on_completed(task)
    retry_tasks = list(manager._bg_tasks)
    assert len(retry_tasks) == 1, "publish 未启动管线时应派生重试任务"

    await manager.shutdown()
    assert retry_tasks[0].cancelled()
    assert manager._bg_tasks == set()


async def test_shutdown_is_idempotent() -> None:
    """连续调用 shutdown() 不得抛错，状态保持已清理。"""
    service = _FakeImageService(block=True)
    manager = _make_manager(service=service)

    await manager.submit(**_submit_kwargs())
    await manager.shutdown()
    assert manager._bg_tasks == set()

    await manager.shutdown()
    assert manager._bg_tasks == set()
    assert manager._notification_queues == {}


async def test_shutdown_marks_drawing_tasks_timeout_and_clears_cooldown() -> None:
    """shutdown() 必须将 drawing 状态任务标记为 timeout 并清除该管线冷却。"""
    service = _FakeImageService(block=True)
    manager = _make_manager(service=service)

    await manager.submit(**_submit_kwargs())
    task = next(iter(manager._tasks.values()))
    assert task.status == "drawing"
    assert manager.check_cooldown("group:1") > 0

    await manager.shutdown()
    assert task.status == "timeout"
    assert manager.check_cooldown("group:1") == 0


async def test_submit_state_machine_busy_then_completed() -> None:
    """提交后任务处于 drawing，重复提交返回 busy，完成后转为 completed。"""
    service = _FakeImageService(block=True)
    hub = _FakeHub(started=True)
    manager = _make_manager(service=service, hub=hub)

    first = json.loads(await manager.submit(**_submit_kwargs()))
    assert first["ok"] is True
    assert first["status"] == "drawing"

    second = json.loads(await manager.submit(**_submit_kwargs()))
    assert second["status"] == "busy"

    service.release.set()
    await asyncio.sleep(0.05)
    task = next(iter(manager._tasks.values()))
    assert task.status == "completed"
    assert task.image_id == "img_test_1"
    assert manager.get_pipeline_status("group:1")["has_active_task"] is False
    assert len(hub.published) == 1


async def test_submit_reports_failure_when_service_raises() -> None:
    """绘图服务抛错时任务必须标记 failed，submit 返回错误并取消冷却。"""
    service = _FakeImageService(fail=RuntimeError("绘图服务爆炸"))
    manager = _make_manager(service=service)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["ok"] is False
    task = next(iter(manager._tasks.values()))
    assert task.status == "failed"
    assert "绘图服务爆炸" in task.error
    assert manager.check_cooldown("group:1") == 0
