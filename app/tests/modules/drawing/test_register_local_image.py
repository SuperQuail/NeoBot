"""Bot 自发图片登记进 temp 图库（fix(2) D3 / F4）。

覆盖：本地文件 → tmp_xxx 记录、产物落在 temp 目录、与「其他人发的图片」
完全相同的按 image_id 取回入口（image_context__add_image 用的就是这条解析路径）、
缺失/超限文件不登记。
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.service import CreatorImageService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


class _FakeModel:
    model_name = "fake-model"
    base_url = "http://model.invalid"
    api_key = "sk-fake"
    settings = SimpleNamespace(timeout_seconds=30, extra_body=None)


def _png_bytes(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _make_service(tmp_path, monkeypatch) -> CreatorImageService:
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'register-test.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(
        "neobot_app.drawing.service.get_registered_model",
        lambda name: _FakeModel(),
    )
    return CreatorImageService(
        uow_factory=make_uow_factory(engine),
        adapter=None,
        config=DrawServiceConfig(gallery_capacity=10, gallery_page_size=50),
        data_dir=tmp_path / "data",
        model_names=["fake-model"],
    )


async def test_register_local_image_is_retrievable_by_image_id(tmp_path, monkeypatch):
    """登记的图片必须能按 tmp_xxx 再取回：与其他人发的图片同一套入口。"""
    service = await _make_service(tmp_path, monkeypatch)
    source = tmp_path / "bot_sent.png"
    source.write_bytes(_png_bytes("blue"))

    record = await service.register_local_image(source)

    assert record is not None
    assert record.image_id.startswith("tmp_")
    assert record.source == "tmp"
    stored = Path(record.file_path)
    assert stored.is_file()
    assert stored.name == f"{record.image_id}.png"

    # image_context__add_image(image_id="tmp_xxx") 走的正是这条解析路径
    resolved = await service._resolve_process_source(record.image_id)
    assert Path(resolved) == Path(stored)


async def test_register_local_image_returns_none_for_missing_file(tmp_path, monkeypatch):
    service = await _make_service(tmp_path, monkeypatch)
    assert await service.register_local_image(tmp_path / "nope.png") is None


async def test_register_local_image_rejects_oversized_file(tmp_path, monkeypatch):
    service = await _make_service(tmp_path, monkeypatch)
    source = tmp_path / "huge.png"
    source.write_bytes(_png_bytes("green"))

    assert await service.register_local_image(source, max_bytes=10) is None


async def test_drawing_manager_exposes_image_service(tmp_path, monkeypatch):
    """ReplyOrchestrator 经 drawing_manager.image_service 取登记入口。"""
    from neobot_app.drawing.manager import BackgroundDrawingManager

    service = await _make_service(tmp_path, monkeypatch)
    manager = BackgroundDrawingManager()
    manager.set_image_service(service)

    assert manager.image_service is service
