"""参考图引用解析：gallery: 前缀、序号与 image_id 两种口径必须一致。"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.service import CreatorImageService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


class _FakeModel:
    model_name = "fake-model"
    base_url = "http://model.invalid"
    api_key = "sk-fake"
    settings = __import__("types").SimpleNamespace(timeout_seconds=30, extra_body=None)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


async def _make_service(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'refs.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    monkeypatch.setattr(
        "neobot_app.drawing.service.get_registered_model",
        lambda name: _FakeModel(),
    )
    service = CreatorImageService(
        uow_factory=uow_factory,
        adapter=None,
        config=DrawServiceConfig(gallery_capacity=10, gallery_page_size=50),
        data_dir=tmp_path / "data",
        model_names=["fake-model"],
    )
    return service, engine, uow_factory


async def _seed(service, uow_factory, image_ids: list[str]) -> None:
    async with uow_factory() as uow:
        for index, image_id in enumerate(image_ids, start=1):
            path = service._gallery_dir / f"{image_id}.png"
            path.write_bytes(_png_bytes())
            await uow.creator_images.set(
                image_id,
                source="gallery",
                file_hash=str(index) * 64,
                file_path=str(path),
                prompt=None,
                description=f"图 {index}",
                mime_type="image/png",
                original_width=4,
                original_height=4,
            )
        await uow.commit()


async def test_gallery_prefix_accepts_both_number_and_image_id(tmp_path, monkeypatch):
    """模型写成 gallery:3 或 gallery:g_xxx 都必须能解析到同一张图。

    这是「参考图生图反复改参数」的直接修复点：此前 gallery:<序号> 会直接失败。
    """
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_first", "g_second"])
        numbers = await service.gallery_number_map()
        assert set(numbers) == {"g_first", "g_second"}
        assert sorted(numbers.values()) == [1, 2]

        for image_id, number in numbers.items():
            by_number = await service._resolve_reference(f"gallery:{number}")
            by_id = await service._resolve_reference(f"gallery:{image_id}")
            plain_id = await service._resolve_reference(image_id)
            assert by_number.startswith("data:image/png;base64,")
            assert by_number == by_id == plain_id
    finally:
        await service.close()
        await engine.dispose()


async def test_number_map_and_reference_lookup_agree(tmp_path, monkeypatch):
    """gallery_list/search 展示的 number 必须与 reference_id 解析出的图一致。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_a", "g_b", "g_c"])
        numbers = await service.gallery_number_map()
        records = await service.list_images(source="gallery", limit=9999, offset=0)

        assert len(records) == 3
        for index, record in enumerate(records, start=1):
            assert numbers[record.image_id] == index
            assert (await service._get_reference_by_number(index)).image_id == record.image_id
    finally:
        await service.close()
        await engine.dispose()


async def test_missing_gallery_reference_reports_clear_error(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_only"])
        with pytest.raises(LookupError) as excinfo:
            await service._resolve_reference("gallery:99")
        assert "序号" in str(excinfo.value)

        with pytest.raises(LookupError) as excinfo:
            await service._resolve_reference("gallery:g_missing")
        assert "image_id" in str(excinfo.value)
    finally:
        await service.close()
        await engine.dispose()


async def test_unknown_reference_lists_supported_formats(tmp_path, monkeypatch):
    """报错必须列出可用格式，模型才能一次改对而不是反复试错。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        with pytest.raises(LookupError) as excinfo:
            await service._resolve_reference("随便写的参考图")
        message = str(excinfo.value)
        for token in ("gallery:", "pool:", "emoji:", "url:", "file:", "chat:"):
            assert token in message
    finally:
        await service.close()
        await engine.dispose()


async def test_pool_source_accepts_gallery_image_id(tmp_path, monkeypatch):
    """image_pool__put(source="gallery:<image_id>") 也要能用稳定主键。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_pool"])
        path = await service.resolve_source_to_path("gallery:g_pool")
        assert path.name == "g_pool.png"

        numbers = await service.gallery_number_map()
        by_number = await service.resolve_source_to_path(f"gallery:{numbers['g_pool']}")
        assert by_number == path
    finally:
        await service.close()
        await engine.dispose()
