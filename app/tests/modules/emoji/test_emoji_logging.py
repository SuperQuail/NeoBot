from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from neobot_app.emoji.service import EmojiService
from neobot_contracts.ports.logging import NullLogger


@pytest.mark.asyncio
async def test_scan_summarizes_database_lookup_failures(tmp_path):
    repository = SimpleNamespace(get_by_hash=AsyncMock(side_effect=RuntimeError("database unavailable")))

    @asynccontextmanager
    async def uow_factory():
        yield SimpleNamespace(emojis=repository, commit=AsyncMock())

    recorder = Mock(spec=NullLogger)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory, logger=recorder)
    service._emoji_dir.mkdir()
    for index, color in enumerate(("red", "green", "blue")):
        Image.new("RGB", (2, 2), color=color).save(service._emoji_dir / f"{index}.png")
    service._parse_batch = AsyncMock(return_value=[])
    service._rebuild_mapping = Mock()
    service._cleanup_stale_emoji_records = AsyncMock()

    await service._scan_folder()

    assert repository.get_by_hash.await_count == 3
    recorder.error.assert_called_once()
    assert recorder.error.call_args.kwargs["failed_count"] == 3
    assert recorder.error.call_args.kwargs["error"] == "database unavailable"


@pytest.mark.asyncio
async def test_empty_scan_reports_only_when_library_becomes_empty(tmp_path):
    recorder = Mock(spec=NullLogger)
    service = EmojiService(data_dir=tmp_path, uow_factory=Mock(), logger=recorder)
    service._emoji_dir.mkdir()
    service._cleanup_stale_emoji_records = AsyncMock()

    await service._scan_folder()
    await service._scan_folder()

    recorder.info.assert_called_once()
    assert service._cleanup_stale_emoji_records.await_count == 2


@pytest.mark.asyncio
async def test_vision_batch_summarizes_errors_and_empty_results(tmp_path):
    recorder = Mock(spec=NullLogger)

    async def respond_to_image(messages):
        # 并发准备图片的完成顺序不固定，响应应跟输入绑定，而非跟调用次序绑定。
        url = messages[0]["content"][1]["image_url"]["url"]
        with Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))) as image:
            red, green, blue = image.convert("RGB").getpixel((0, 0))
        if red > green and red > blue:
            raise RuntimeError("provider unavailable")
        return {"content": "" if green > blue else "描述"}

    provider = SimpleNamespace(chat=AsyncMock(side_effect=respond_to_image))
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=Mock(),
        logger=recorder,
        vision_provider=provider,
    )
    service._emoji_dir.mkdir()
    items = []
    for index, color in enumerate(("red", "green", "blue")):
        path = service._emoji_dir / f"{index}.png"
        Image.new("RGB", (2, 2), color=color).save(path)
        items.append((str(index), path))

    results = await service._parse_batch(items)

    assert [result[2] for result in results] == ["[解析失败]", "[解析失败]", "描述"]
    recorder.warning.assert_called_once()
    assert recorder.warning.call_args.kwargs["failed_count"] == 2
    assert recorder.warning.call_args.kwargs["total_count"] == 3
