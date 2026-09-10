"""图片预处理必须离开事件循环。

prepare_local_image 会 read_bytes + PIL 解码 + LANCZOS 重采样重编码；
resolve_local_image（每条带图消息都会走）以前直接同步调用它，慢盘/大图会卡住
整个事件循环。emoji 的多数入口与 gallery 也在 async 上下文里同步调用过它。
"""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

from neobot_app.message import image_pipeline as pipeline


def _make_png(path: Path, size: tuple[int, int] = (32, 32)) -> Path:
    Image.new("RGB", size, (200, 30, 30)).save(path)
    return path


async def test_prepare_local_image_async_runs_in_worker_thread(
    tmp_path: Path, monkeypatch
) -> None:
    loop_thread = threading.get_ident()
    source = _make_png(tmp_path / "a.png")
    seen: list[int] = []
    original = pipeline.prepare_local_image

    def _spy(*args, **kwargs):
        seen.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "prepare_local_image", _spy)

    prepared = await pipeline.prepare_local_image_async(source)

    assert prepared.file_hash
    assert seen and seen[0] != loop_thread


async def test_resolve_local_image_does_not_block_loop(
    tmp_path: Path, monkeypatch
) -> None:
    loop_thread = threading.get_ident()
    source = _make_png(tmp_path / "b.png")
    seen: list[int] = []
    original = pipeline.prepare_local_image

    def _spy(*args, **kwargs):
        seen.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "prepare_local_image", _spy)

    class _AnalysisService:
        async def get(self, file_hash: str):
            return None

    preparer = pipeline.ImagePromptPreparer(_AnalysisService())
    resolution = await preparer.resolve_local_image(source)

    assert resolution.cached_analysis is None
    assert resolution.prepared.file_hash
    assert seen and seen[0] != loop_thread


async def test_async_variant_matches_sync_hash(tmp_path: Path) -> None:
    """线程化不得改变结果：hash/尺寸与同步版本一致。"""
    source = _make_png(tmp_path / "c.png", (64, 48))

    sync_prepared = pipeline.prepare_local_image(source)
    async_prepared = await pipeline.prepare_local_image_async(source)

    assert async_prepared.file_hash == sync_prepared.file_hash
    assert async_prepared.mime_type == sync_prepared.mime_type
    assert (
        async_prepared.processed_width,
        async_prepared.processed_height,
    ) == (sync_prepared.processed_width, sync_prepared.processed_height)
