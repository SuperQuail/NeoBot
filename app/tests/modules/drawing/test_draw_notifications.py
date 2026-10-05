"""绘图通知的 JSON 契约：字段齐全、后续工具名与参数可直接照抄。"""

from __future__ import annotations

import json

import pytest

from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.manager import BackgroundDrawingManager
from neobot_app.drawing.tasks import DrawTask


class _CapturingManager(BackgroundDrawingManager):
    """把通知截获下来，不真正推送。"""

    def __init__(self, config: DrawServiceConfig | None = None) -> None:
        super().__init__(config=config or DrawServiceConfig())
        self.notifications: list[str] = []

    async def _push_notification(self, task, notification: str) -> None:  # type: ignore[override]
        self.notifications.append(notification)

    @property
    def last(self) -> dict:
        assert self.notifications, "没有产生通知"
        return json.loads(self.notifications[-1])


def _task(**overrides) -> DrawTask:
    task = DrawTask(
        task_id="draw_abc123",
        pipeline_key="group:817885947",
        conversation_kind="group",
        conversation_id="817885947",
        prompt="参考图中角色坐在图书馆看书",
        requester="唐天",
        requirements="画一张看书图",
    )
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


@pytest.mark.asyncio
async def test_completed_notification_is_json_with_real_tool_calls():
    manager = _CapturingManager()
    task = _task()
    task.status = "completed"
    task.image_id = "tmp_9c31af"
    task.record_payload = {
        "image_id": "tmp_9c31af",
        "source": "tmp",
        "file_path": "/data/tmp/tmp_9c31af.png",
        "width": 1024,
        "height": 1024,
    }

    await manager._on_completed(task)
    payload = manager.last

    assert payload["ok"] is True
    assert payload["kind"] == "draw_result"
    assert payload["status"] == "completed"
    assert payload["image_id"] == "tmp_9c31af"
    assert payload["file_path"] == "/data/tmp/tmp_9c31af.png"
    assert payload["request"]["requester"] == "唐天"

    actions = {item.get("action"): item for item in payload["next"]}
    # 工具名必须是真实存在的：曾写成 image_send__send / gallery__add，模型照着调必然失败
    send = actions["send_image"]
    assert send["tool"] == "image_send__send_image"
    assert send["args"]["file_path"] == "/data/tmp/tmp_9c31af.png"
    assert send["args"]["group_id"] == "817885947"
    # 临时图不在图库里，不能再用 image_id / source 这套已废弃写法
    assert "image_id" not in send["args"]
    assert "source" not in send["args"]

    save = actions["save_to_gallery"]
    assert save["tool"] == "gallery__gallery_add"
    assert save["args"]["image_path"] == "/data/tmp/tmp_9c31af.png"


@pytest.mark.asyncio
async def test_private_conversation_uses_user_id():
    manager = _CapturingManager()
    task = _task(
        conversation_kind="private", conversation_id="3331347593",
        pipeline_key="private:3331347593",
    )
    task.status = "completed"
    task.image_id = "tmp_1"
    task.record_payload = {"file_path": "/data/tmp/tmp_1.png"}

    await manager._on_completed(task)
    send = next(
        item for item in manager.last["next"] if item.get("action") == "send_image"
    )
    assert send["args"]["user_id"] == "3331347593"
    assert "group_id" not in send["args"]


@pytest.mark.asyncio
async def test_failed_notification_is_json_false_with_error():
    manager = _CapturingManager()
    task = _task()
    task.status = "failed"
    task.error = '{"error_type": "LookupError", "message": "无法解析参考图"}'

    await manager._on_failed(task)
    payload = manager.last

    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "无法解析参考图" in payload["error"]
    assert payload["next"][0]["action"] == "reply_to_user"


@pytest.mark.asyncio
async def test_notifications_no_longer_use_answer_wrapper():
    """去掉 <这是新的必须要回答的内容> 包裹：正常结果通知不应强制改变模型行为。"""
    manager = _CapturingManager()
    task = _task()
    task.status = "failed"
    task.error = "boom"
    await manager._on_failed(task)
    await manager._on_completed(_task(status="completed", image_id="tmp_x"))

    for text in manager.notifications:
        assert "这是新的必须要回答的内容" not in text
        assert json.loads(text)["kind"].startswith("draw_result")


@pytest.mark.asyncio
async def test_retry_notification_keeps_attempt_and_next_actions():
    manager = _CapturingManager()
    task = _task()
    task.status = "completed"
    task.image_id = "tmp_y"
    task.record_payload = {"file_path": "/data/tmp/tmp_y.png"}
    task.notification_count = 2
    task.notified = False

    # 直接构造重试通知载荷，避免等待重试定时器
    payload = json.loads(
        manager._notification_payload(
            task,
            kind="draw_result_retry",
            status="completed",
            message="重复提醒",
            attempt=2,
        )
    )

    assert payload["attempt"] == 2
    assert any(item.get("action") == "send_image" for item in payload["next"])
    assert not manager.notifications  # 未触发真实推送


# ── 通知重试耗尽后的终态通知（issue #76）─────────────────────────


class _StubHub:
    """最小通知中心替身：终态分支只在 `_notification_hub is not None` 时才发通知。"""

    def get_pipeline_status(self, _key: str) -> dict:
        return {"background_notifications_by_source": {}}

    async def publish(self, **_kwargs) -> bool:  # pragma: no cover - 被下面的覆写截住
        return True


def _fast_manager() -> "_CapturingManager":
    """重试窗口压到 0：直接跑出「重试耗尽」的终态分支，不用等定时器。"""
    manager = _CapturingManager(
        DrawServiceConfig(draw_max_retries=0, draw_notification_retry_seconds=0)
    )
    manager._notification_hub = _StubHub()

    async def _capture(task, notification: str) -> bool:
        manager.notifications.append(notification)
        return True

    manager._publish_hub_notification = _capture  # type: ignore[method-assign]
    return manager


@pytest.mark.asyncio
async def test_failed_task_after_retry_exhaustion_still_reports_failure():
    """失败任务在重试耗尽后必须**仍报失败**（issue #76）。

    此前该分支无条件用 `status="completed"` + 「图片已生成」—— 绘图 API 超时之类
    的失败会被说成成功（`ok: true`），用户侧表现为「静默失败」。
    """
    manager = _fast_manager()
    task = _task(status="failed", error='{"error_type": "ReadTimeout", "message": "timed out"}')
    task.notified = False

    await manager._retry_notification(task)

    payload = manager.last
    assert payload["kind"] == "draw_result_timeout"
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "图片已生成" not in payload["message"]
    assert "失败" in payload["message"]
    # 失败原因保留，任务状态**不被改写**成 timeout
    assert payload["error"]
    assert task.status == "failed"
    assert task.notification_timed_out is True


@pytest.mark.asyncio
async def test_completed_task_after_retry_exhaustion_still_reports_success():
    """成功任务保持原样：不能因为修失败路径把成功也说成失败。"""
    manager = _fast_manager()
    task = _task(status="completed", image_id="tmp_z")
    task.record_payload = {"image_id": "tmp_z", "file_path": "/data/tmp/tmp_z.png"}
    task.notified = False

    await manager._retry_notification(task)

    payload = manager.last
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert "已生成" in payload["message"]
    assert task.status == "completed"
    assert task.notification_timed_out is True
