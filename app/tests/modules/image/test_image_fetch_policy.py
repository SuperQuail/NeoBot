"""图片拉取策略：并发 + 统一 15 秒超时（issue #80 的追加优化）。

带消息预热时正文里可能同时挂着多张「永远拉不到」的历史图片：串行拉取会把每张的超时
叠起来（4 张 × 30 秒 = 一轮 120 秒纯等待，正好吃掉群聊静默预算）。这里锁两件事：
**并发**（最坏只等一次超时）与**统一 15 秒**（超时单价降半）。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from neobot_app.image.parser import ImageParseService
from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS, ImageSourceResolver
from neobot_app.image.unavailable import ImageUnavailableRegistry
from neobot_app.reply.vision_context import ReplyVisionContext
from neobot_app.skills import vision_detect_skill
from neobot_app.skills.image_context_skill import ImageContextResult, ImageContextSkill


def test_fetch_timeout_constant_is_15_seconds() -> None:
    assert IMAGE_FETCH_TIMEOUT_SECONDS == 15.0
    assert vision_detect_skill._MAX_IMAGE_TIMEOUT == IMAGE_FETCH_TIMEOUT_SECONDS


def test_resolver_uses_the_shared_timeout(monkeypatch) -> None:
    """取图解析器把 15 秒传给 HTTP 客户端（而不是各自的 30 秒字面量）。"""
    seen: list[float] = []

    def client(**kwargs):
        seen.append(float(kwargs["timeout"]))
        raise AssertionError("只校验超时参数，不真的发请求")

    monkeypatch.setattr("neobot_app.image.source.image_http_client", client)
    resolver = ImageSourceResolver(unavailable_registry=ImageUnavailableRegistry())

    async def run() -> None:
        await resolver._download_image_segment({"url": "https://images.test/x.png"})

    asyncio.run(run())
    assert seen == [IMAGE_FETCH_TIMEOUT_SECONDS]


def test_parser_uses_the_shared_timeout(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    get_image = AsyncMock(return_value={"data": {}})
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    service = ImageParseService()
    service._analysis = None

    asyncio.run(service._parse_single_image({"type": "image", "data": {"file": "f"}}))
    get_image.assert_awaited_once_with("f", timeout=IMAGE_FETCH_TIMEOUT_SECONDS)


def test_image_context_tool_default_timeout_is_15() -> None:
    tool = ImageContextSkill().get_tools()[0]
    schema = tool["function"]["parameters"]["properties"]["timeout_seconds"]
    assert schema["default"] == 15


async def test_refresh_defaults_loads_images_concurrently() -> None:
    """4 张图并发拉取：耗时≈单张（串行会 ≥4 倍）。"""
    entries = [
        SimpleNamespace(
            message=SimpleNamespace(message_id=i, message=[{"type": "image"}]),
            replied_messages=[],
        )
        for i in range(1, 5)
    ]
    queue = SimpleNamespace(entries=lambda _key: entries)
    numbering = SimpleNamespace(mapping={i: i for i in range(1, 5)})

    async def execute(_name, args):
        await asyncio.sleep(0.2)
        return ImageContextResult(
            '{"ok": true}',
            [{"type": "image_url", "image_url": {"url": f"image-{args['msg_number']}"}}],
        )

    context = ReplyVisionContext()
    started = time.monotonic()
    await context.refresh_defaults(
        queue=queue,
        queue_key="1",
        numbering=numbering,
        loader=SimpleNamespace(execute=execute),
        pipeline_key="group:1",
        max_images=4,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.6, f"4 张图应当并发拉取（串行 ≥0.8s），实测 {elapsed:.2f}s"
    parts = context.request_messages([])[-1]["content"]
    loaded = sorted(p["image_url"]["url"] for p in parts if p["type"] == "image_url")
    assert loaded == [f"image-{i}" for i in range(1, 5)]


async def test_parse_and_replace_parses_images_concurrently() -> None:
    """一条消息里的多张图并发解析：耗时≈单张。"""
    service = ImageParseService()

    async def slow_parse(segment):
        await asyncio.sleep(0.2)
        return f"[图片：{segment['data']['file']}]"

    service._parse_single_image = slow_parse
    message = SimpleNamespace(message=[{"type": "image", "data": {"file": f"f{i}"}} for i in range(3)])
    started = time.monotonic()
    await service._parse_and_replace(message, [0, 1, 2])
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"3 张图应当并发解析（串行 ≥0.6s），实测 {elapsed:.2f}s"
    assert [seg.data["text"] for seg in message.message] == [
        "[图片：f0]",
        "[图片：f1]",
        "[图片：f2]",
    ]
