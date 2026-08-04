"""ImageParseService 测试：_pending 清理、wait_for_queue 语义、多 key 隔离、超时与任务失败回调。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.image.parser import ImageParseService


def _group_message(message_id: int, *segments: tuple[str, dict]) -> GroupMessage:
    """构造带指定消息段的群消息。"""
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(user_id=7, nickname="tester"),
        message=[MessageSegment(type=t, data=d) for t, d in segments],
        raw_message="",
    )


def _make_service(**kwargs) -> ImageParseService:
    """构造解析服务，并注入一个固定返回描述的 _parse_single_image 桩。"""
    service = ImageParseService(**kwargs)
    service._parse_single_image = AsyncMock(return_value="[图片：自动解析结果]")
    return service


async def test_parse_message_images_replaces_image_segments_with_description() -> None:
    """Arrange: 含 image 与 cardimage 段的消息；Act: parse_message_images 后等待完成；Assert: 两个图片段均被文本段替换且 _pending 清空。"""
    message = _group_message(
        1,
        ("image", {"file": "a.jpg"}),
        ("text", {"text": "保留"}),
        ("cardimage", {"file": "b.jpg"}),
    )
    service = _make_service()

    await service.parse_message_images(message, "k")
    await service.wait_for_queue("k")

    assert message.message[0].type == "text"
    assert message.message[0].data["text"] == "[图片：自动解析结果]"
    assert message.message[1].type == "text"
    assert message.message[2].type == "text"
    assert service._pending == {}


async def test_pending_key_disappears_after_parse_completes() -> None:
    """Arrange: 解析一条含图片的消息；Act: 循环让出事件循环直至任务完成；Assert: _pending 中对应 key 自动消失。"""
    message = _group_message(2, ("image", {"file": "a.jpg"}))
    service = _make_service()

    await service.parse_message_images(message, "k")
    assert "k" in service._pending

    for _ in range(100):
        if not service._pending:
            break
        await asyncio.sleep(0)
    assert service._pending == {}


async def test_wait_for_queue_timeout_cancels_pending_tasks_without_raising() -> None:
    """Arrange: 解析被挂起的慢任务；Act: 以极短 timeout 调用 wait_for_queue；Assert: 不抛异常、key 被移除、任务被取消且图片段未被替换。"""
    release = asyncio.Event()

    async def slow_parse(_segment):
        await release.wait()
        return "[图片：自动解析结果]"

    service = ImageParseService()
    service._parse_single_image = AsyncMock(side_effect=slow_parse)
    message = _group_message(3, ("image", {"file": "a.jpg"}))
    await service.parse_message_images(message, "k")

    await service.wait_for_queue("k", timeout=0.05)

    assert service._pending == {}
    assert message.message[0].type == "image"


async def test_multiple_keys_isolated_waiting_one_does_not_affect_other() -> None:
    """Arrange: key A 慢任务、key B 快任务；Act: 等待 B 完成；Assert: B 的 key 已清理而 A 仍在 _pending。"""
    release = asyncio.Event()

    async def controllable_parse(segment):
        if segment.data.get("file") == "slow.jpg":
            await release.wait()
        return "[图片：快速完成]"

    service = ImageParseService()
    service._parse_single_image = AsyncMock(side_effect=controllable_parse)

    slow = _group_message(4, ("image", {"file": "slow.jpg"}))
    fast = _group_message(5, ("image", {"file": "fast.jpg"}))
    await service.parse_message_images(slow, "slow")
    await service.parse_message_images(fast, "fast")

    await service.wait_for_queue("fast")
    assert "fast" not in service._pending
    assert "slow" in service._pending

    release.set()
    await service.wait_for_queue("slow")
    assert service._pending == {}


async def test_parse_single_image_failure_replaces_segment_with_error_text() -> None:
    """Arrange: _parse_single_image 抛异常的桩；Act: parse_message_images 并等待；Assert: 图片段被替换为失败文案且任务被清理。"""
    message = _group_message(6, ("image", {"file": "boom.jpg"}))
    service = ImageParseService()
    service._parse_single_image = AsyncMock(side_effect=RuntimeError("boom"))

    await service.parse_message_images(message, "k")
    await service.wait_for_queue("k")

    assert message.message[0].type == "text"
    assert message.message[0].data["text"] == "[图片解析失败]"
    assert service._pending == {}


async def test_parse_message_images_without_images_creates_no_task() -> None:
    """Arrange: 纯文本消息；Act: parse_message_images；Assert: 不创建任务、_pending 为空且消息不变。"""
    message = _group_message(7, ("text", {"text": "no image"}))
    service = _make_service()

    await service.parse_message_images(message, "k")

    assert service._pending == {}
    assert message.message[0].type == "text"


async def test_concurrent_parse_many_keys_complete_independently() -> None:
    """Arrange: 5 个 key 各含一张图片、解析时长错开；Act: gather 并发解析后分别等待；Assert: 每张图都被替换且各 key 互不干扰。"""
    delays = {"k0": 0.05, "k1": 0.01, "k2": 0.03, "k3": 0.0, "k4": 0.02}
    service = ImageParseService()

    # 固定解析时长序列，避免依赖 dict 顺序
    ordered_delays = [0.05, 0.01, 0.03, 0.0, 0.02]
    counter = {"i": 0}

    async def delayed_parse(_segment):
        index = counter["i"]
        counter["i"] += 1
        await asyncio.sleep(ordered_delays[index % len(ordered_delays)])
        return "[图片：并发解析]"

    service._parse_single_image = AsyncMock(side_effect=delayed_parse)
    messages = {
        key: _group_message(100 + index, ("image", {"file": f"{key}.jpg"}))
        for index, key in enumerate(delays)
    }

    await asyncio.gather(
        *(service.parse_message_images(messages[key], key) for key in delays)
    )
    await asyncio.gather(*(service.wait_for_queue(key) for key in delays))

    for key, message in messages.items():
        assert message.message[0].type == "text"
        assert message.message[0].data["text"] == "[图片：并发解析]"
    assert service._pending == {}


async def test_wait_for_queue_with_unknown_key_is_noop() -> None:
    """Arrange: 无任何待处理任务的解析服务；Act: 等待不存在的 key；Assert: 静默返回且 _pending 不变。"""
    service = _make_service()

    await service.wait_for_queue("never-existed")

    assert service._pending == {}
