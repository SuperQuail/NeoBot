"""CreatorImageService 图库查询轻量化、close 幂等与引用解析安全测试。"""

from __future__ import annotations

import io
import os
from types import SimpleNamespace

import httpx
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
    settings = SimpleNamespace(timeout_seconds=30, extra_body=None)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


async def _make_service(tmp_path, monkeypatch) -> tuple[CreatorImageService, object, object]:
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'gallery-test.sqlite3').as_posix()}")
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
    )
    return service, engine, uow_factory


def _explode(*args, **kwargs):
    raise AssertionError("查询路径不应触发全量哈希")


async def _always_public(url: str) -> bool:
    return True


async def test_list_images_does_not_hash_disk_files(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        img = service._gallery_dir / "g_abc.png"
        img.write_bytes(_png_bytes())
        async with uow_factory() as uow:
            await uow.creator_images.set(
                "g_abc",
                source="gallery",
                file_hash="h" * 64,
                file_path=str(img),
                prompt=None,
                description="测试图片",
                mime_type="image/png",
                original_width=4,
                original_height=4,
            )
            await uow.commit()

        monkeypatch.setattr("neobot_app.drawing.service.prepare_local_image", _explode)
        records = await service.list_images(source="gallery")
        assert [r.image_id for r in records] == ["g_abc"]
    finally:
        await service.close()
        await engine.dispose()


async def test_list_images_excludes_dead_records(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        live = service._gallery_dir / "g_live.png"
        live.write_bytes(_png_bytes())
        dead = service._gallery_dir / "g_dead.png"
        async with uow_factory() as uow:
            for image_id, path in (("g_live", live), ("g_dead", dead)):
                await uow.creator_images.set(
                    image_id,
                    source="gallery",
                    file_hash="h" * 64,
                    file_path=str(path),
                    prompt=None,
                    description="x",
                    mime_type="image/png",
                    original_width=4,
                    original_height=4,
                )
            await uow.commit()

        monkeypatch.setattr("neobot_app.drawing.service.prepare_local_image", _explode)
        records = await service.list_images(source="gallery")
        assert {r.image_id for r in records} == {"g_live"}
    finally:
        await service.close()
        await engine.dispose()


async def test_count_images_does_not_hash(tmp_path, monkeypatch):
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr("neobot_app.drawing.service.prepare_local_image", _explode)
        assert await service.count_images() == 0
    finally:
        await service.close()
        await engine.dispose()


async def test_search_images_excludes_dead_records(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        live = service._gallery_dir / "g_live.png"
        live.write_bytes(_png_bytes())
        dead = service._gallery_dir / "g_dead.png"
        async with uow_factory() as uow:
            for image_id, path in (("g_live", live), ("g_dead", dead)):
                await uow.creator_images.set(
                    image_id,
                    source="gallery",
                    file_hash="h" * 64,
                    file_path=str(path),
                    prompt=None,
                    description="红色",
                    mime_type="image/png",
                    original_width=4,
                    original_height=4,
                )
            await uow.commit()

        monkeypatch.setattr("neobot_app.drawing.service.prepare_local_image", _explode)
        records = await service.search_images("红色", source="gallery", limit=50)
        assert {r.image_id for r in records} == {"g_live"}
    finally:
        await service.close()
        await engine.dispose()


async def test_close_is_idempotent_and_cancels_cleanup_task(tmp_path, monkeypatch):
    """close() 必须取消清理任务并关闭两个 httpx client，且重复调用不抛错。"""
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        await service.start()
        assert service._cleanup_task is not None, "start() 后应注册清理任务"

        await service.close()
        assert service._cleanup_task is None, "close() 后清理任务应被取消并置空"
        assert service._client.is_closed
        assert service._public_client.is_closed

        await service.close()
    finally:
        await engine.dispose()


async def test_url_reference_rejects_private_address_without_request(tmp_path, monkeypatch):
    """url: 引用指向内网地址时必须被 SSRF 校验拒绝，且不发起任何 HTTP 请求。"""
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        def _explode_get(*args, **kwargs):
            raise AssertionError("内网地址不应触发 HTTP 请求")

        service._public_client.get = _explode_get  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="非公网地址"):
            await service._resolve_reference("url:http://127.0.0.1:8080/pic.png")
    finally:
        await service.close()
        await engine.dispose()


async def test_url_reference_request_has_no_authorization_header(tmp_path, monkeypatch):
    """url: 引用下载必须走无凭据 client，请求头不得携带 Authorization。"""
    seen_headers: list[httpx.Headers] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(
            200, content=_png_bytes(), headers={"content-type": "image/png"}
        )

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "neobot_app.drawing.service.httpx.AsyncClient",
        lambda **kw: real_async_client(**kw, transport=transport),
    )
    monkeypatch.setattr(
        "neobot_app.utils.ssrf.validate_public_url_async",
        _always_public,
    )
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        data_url = await service._resolve_reference("url:https://example.com/pic.png")
        assert data_url.startswith("data:image/png;base64,")
        assert len(seen_headers) == 1
        header_names = {k.lower() for k in seen_headers[0]}
        assert "authorization" not in header_names
    finally:
        await service.close()
        await engine.dispose()


async def test_file_reference_rejects_path_outside_creator_dir(tmp_path, monkeypatch):
    """file: 引用指向 creator 数据目录之外时必须被拒绝并抛出 PermissionError。"""
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        outside = tmp_path / "outside.png"
        outside.write_bytes(_png_bytes())
        with pytest.raises(PermissionError, match="越界"):
            await service._resolve_reference(f"file:{outside}")
        with pytest.raises(PermissionError, match="越界"):
            await service.resolve_source_to_path(f"file:{outside}")
    finally:
        await service.close()
        await engine.dispose()


async def test_file_reference_accepts_path_inside_creator_dir(tmp_path, monkeypatch):
    """file: 引用位于 creator 目录（gallery/tmp）内时应正常解析为 data URL。"""
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        inside = service._gallery_dir / "g_inside.png"
        inside.write_bytes(_png_bytes())
        data_url = await service._resolve_reference(f"file:{inside}")
        assert data_url.startswith("data:image/png;base64,")
        resolved = await service.resolve_source_to_path(f"file:{inside}")
        assert resolved == inside.resolve()
    finally:
        await service.close()
        await engine.dispose()


async def test_query_paths_do_not_trigger_full_hash_with_disk_files(tmp_path, monkeypatch):
    """磁盘已有图片文件与记录时，count/list/search 查询仍不得触发全量哈希。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        img = service._gallery_dir / "g_abc.png"
        img.write_bytes(_png_bytes())
        async with uow_factory() as uow:
            await uow.creator_images.set(
                "g_abc",
                source="gallery",
                file_hash="h" * 64,
                file_path=str(img),
                prompt=None,
                description="测试图片",
                mime_type="image/png",
                original_width=4,
                original_height=4,
            )
            await uow.commit()

        monkeypatch.setattr("neobot_app.drawing.service.prepare_local_image", _explode)
        assert await service.count_images(source="gallery") == 1
        assert [r.image_id for r in await service.list_images(source="gallery")] == ["g_abc"]
        assert {r.image_id for r in await service.search_images("测试", source="gallery")} == {"g_abc"}
    finally:
        await service.close()
        await engine.dispose()


async def test_dedup_keeps_newest_file(tmp_path, monkeypatch):
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        gallery = service._gallery_dir
        old = gallery / "old.png"
        new = gallery / "new.png"
        payload = _png_bytes()
        old.write_bytes(payload)
        new.write_bytes(payload)
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))

        await service._cleanup_stale_records()

        assert not old.exists(), "应删除较旧的重复文件"
        assert new.exists(), "应保留较新的文件"
    finally:
        await service.close()
        await engine.dispose()


async def test_dedup_keeps_newest_sidecar(tmp_path, monkeypatch):
    service, engine, _ = await _make_service(tmp_path, monkeypatch)
    try:
        gallery = service._gallery_dir
        old = gallery / "old.png"
        new = gallery / "new.png"
        payload = _png_bytes()
        old.write_bytes(payload)
        new.write_bytes(payload)
        old.with_suffix(".txt").write_text("旧描述", encoding="utf-8")
        new.with_suffix(".txt").write_text("新描述", encoding="utf-8")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))

        await service._cleanup_stale_records()

        assert not old.exists()
        assert new.exists()
        assert (new.with_suffix(".txt")).read_text("utf-8") == "新描述"
    finally:
        await service.close()


async def _seed_gallery(service, uow_factory, image_id: str, description: str, prompt: str = "") -> None:
    path = service._gallery_dir / f"{image_id}.png"
    path.write_bytes(_png_bytes())
    async with uow_factory() as uow:
        await uow.creator_images.set(
            image_id,
            source="gallery",
            file_hash="h" * 64 + image_id[:4],
            file_path=str(path),
            prompt=prompt or description,
            description=description,
            mime_type="image/png",
            original_width=4,
            original_height=4,
        )
        await uow.commit()


async def test_search_images_multi_keyword_ranks_full_matches(tmp_path, monkeypatch):
    """多关键词搜索:全部命中的记录排在最前。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed_gallery(service, uow_factory, "g_full", "弥音 立绘 站姿")
        await _seed_gallery(service, uow_factory, "g_part", "弥音 头像")
        await _seed_gallery(service, uow_factory, "g_other", "风景照片")

        records = await service.search_images("弥音 立绘", source="gallery", limit=10)
        ids = [r.image_id for r in records]
        assert ids[0] == "g_full", "全部关键词命中的应排最前"
        assert "g_part" in ids
        assert "g_other" not in ids
    finally:
        await service.close()
        await engine.dispose()


async def test_process_image_resize_and_crop(tmp_path, monkeypatch):
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        await _seed_gallery(service, uow_factory, "g_src", "源图片")

        resized = await service.process_image(
            image="gallery:1", operation="resize", width=20
        )
        assert resized.source == "tmp"
        from PIL import Image

        with Image.open(resized.file_path) as img:
            assert img.size == (20, 20), f"等比缩放 4x4 → 20x20,实际 {img.size}"

        cropped = await service.process_image(
            image="gallery:1", operation="crop", crop_box=[0, 0, 2, 2]
        )
        with Image.open(cropped.file_path) as img:
            assert img.size == (2, 2)
    finally:
        await service.close()
        await engine.dispose()


async def test_process_image_remove_background(tmp_path, monkeypatch):
    """纯色背景去底:键色区域变透明,主体保留。"""
    service, engine, uow_factory = await _make_service(tmp_path, monkeypatch)
    try:
        # 构造:绿色背景 + 中心红色方块
        import io as _io

        buffer = _io.BytesIO()
        img = Image.new("RGB", (10, 10), (0, 255, 0))
        for x in range(3, 7):
            for y in range(3, 7):
                img.putpixel((x, y), (255, 0, 0))
        img.save(buffer, format="PNG")
        path = service._tmp_dir / "g_src_bg.png"
        path.write_bytes(buffer.getvalue())
        async with uow_factory() as uow:
            await uow.creator_images.set(
                "tmp_bg",
                source="tmp",
                file_hash="f" * 64,
                file_path=str(path),
                prompt=None,
                description="背景图",
                mime_type="image/png",
                original_width=10,
                original_height=10,
            )
            await uow.commit()

        result = await service.process_image(
            image="tmp_bg", operation="remove_background", background_color="#00ff00"
        )
        with Image.open(result.file_path) as out:
            assert out.mode == "RGBA"
            corner = out.getpixel((0, 0))
            center = out.getpixel((5, 5))
            assert corner[3] == 0, f"角落应透明,实际 {corner}"
            assert center[3] > 200, f"中心主体应保留,实际 {center}"
    finally:
        await service.close()
        await engine.dispose()
        await engine.dispose()
