"""参考图引用解析：gallery: 前缀、固定编号与 image_id 两种口径必须一致。"""

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
                gallery_no=index,
            )
        await uow.commit()


async def _add_gallery_image(service, image_id: str, description: str):
    """走服务真实入库路径，让编号由服务分配。"""
    path = service._gallery_dir / f"{image_id}.png"
    path.write_bytes(_png_bytes())
    return await service._upsert_record(
        image_id,
        source="gallery",
        file_path=path,
        prompt=None,
        description=description,
    )


async def test_gallery_prefix_accepts_both_number_and_image_id(tmp_path, monkeypatch):
    """模型写成 gallery:3 或 gallery:g_xxx 都必须能解析到同一张图。

    这是「参考图生图反复改参数」的直接修复点：此前 gallery:<序号> 会直接失败。
    """
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_first", "g_second"])
        records = await service.list_images(source="gallery", limit=9999, offset=0)
        numbers = {record.image_id: record.gallery_no for record in records}
        assert numbers == {"g_first": 1, "g_second": 2}

        for image_id, number in numbers.items():
            by_number = await service._resolve_reference(f"gallery:{number}")
            by_id = await service._resolve_reference(f"gallery:{image_id}")
            plain_id = await service._resolve_reference(image_id)
            assert by_number.startswith("data:image/png;base64,")
            assert by_number == by_id == plain_id
    finally:
        await service.close()
        await engine.dispose()


async def test_gallery_no_lookup_agrees_with_records(tmp_path, monkeypatch):
    """gallery_list/search 展示的 gallery_no 必须与 reference_id 解析出的图一致。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_a", "g_b", "g_c"])
        records = await service.list_images(source="gallery", limit=9999, offset=0)

        assert len(records) == 3
        assert sorted(record.gallery_no for record in records) == [1, 2, 3]
        for record in records:
            found = await service._get_reference_by_gallery_no(record.gallery_no)
            assert found.image_id == record.image_id
        # 编号与列表顺序无关：第二张图无论排在哪儿都是 2 号
        assert (await service._get_reference_by_gallery_no(2)).image_id == "g_b"
    finally:
        await service.close()
        await engine.dispose()


async def test_gallery_number_is_assigned_once_and_never_floats(tmp_path, monkeypatch):
    """固定编号：入库分配一次，改描述/删除都不会让编号指到别的图片。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        first = await _add_gallery_image(service, "g_one", "一")
        second = await _add_gallery_image(service, "g_two", "二")
        assert (first.gallery_no, second.gallery_no) == (1, 2)

        # 改描述会刷新 updated_at、翻转列表顺序，但编号必须不变
        updated = await service.update_image_description(image_id="g_one", description="一改")
        assert updated.gallery_no == 1
        records = await service.list_images(source="gallery", limit=9999, offset=0)
        assert [record.image_id for record in records] == ["g_one", "g_two"]
        assert {record.image_id: record.gallery_no for record in records} == {
            "g_one": 1,
            "g_two": 2,
        }

        # 删除 1 号后：2 号仍是 2 号，新图拿 3（已删除的编号不回收）
        assert await service.gallery_delete(image_id="g_one") is True
        third = await _add_gallery_image(service, "g_three", "三")
        assert third.gallery_no == 3
        assert (await service._get_reference_by_gallery_no(2)).image_id == "g_two"
        assert await service._get_reference_by_gallery_no(1) is None
    finally:
        await service.close()
        await engine.dispose()


async def test_missing_gallery_reference_reports_clear_error(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed(service, uow_factory, ["g_only"])
        with pytest.raises(LookupError) as excinfo:
            await service._resolve_reference("gallery:99")
        assert "图库编号" in str(excinfo.value)

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

        records = await service.list_images(source="gallery", limit=9999, offset=0)
        by_number = await service.resolve_source_to_path(f"gallery:{records[0].gallery_no}")
        assert by_number == path
    finally:
        await service.close()
        await engine.dispose()
