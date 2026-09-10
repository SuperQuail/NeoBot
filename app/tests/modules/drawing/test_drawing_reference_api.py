"""参考图生图：默认走 /images/edits（multipart），失败回退 /images/generations。"""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from neobot_app.drawing.config import DrawServiceConfig, ImageGenerationError
from neobot_app.drawing.service import CreatorImageService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


class _Model:
    def __init__(self, **overrides) -> None:
        self.name = "image-model"
        self.model_name = "gpt-image-2.5-flare"
        self.base_url = "http://model.invalid/v1"
        self.api_key = "sk-test"
        self.description = "测试生图模型"
        self.provider_name = "StubProvider"
        self.settings = SimpleNamespace(
            timeout_seconds=30,
            extra_body=None,
            image_api="auto",
            image_reference_param="image",
        )
        for key, value in overrides.items():
            setattr(self, key, value)


def _png_bytes(color: str = "red", size: tuple[int, int] = (8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _data_url(raw: bytes | None = None, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw or _png_bytes()).decode()


def _image_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"b64_json": base64.b64encode(_png_bytes("blue")).decode()}]},
    )


def _reference_file(service, tmp_path, name: str = "ref.png", color: str = "red") -> str:
    """在 creator 数据目录里放一张参考图，返回 file: 引用。"""
    path = service._tmp_dir / name
    path.write_bytes(_png_bytes(color))
    return f"file:{path}"


async def _make_service(tmp_path, monkeypatch, model, handler):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'ref-api.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    monkeypatch.setattr(
        "neobot_app.drawing.service.get_registered_model", lambda name: model
    )
    service = CreatorImageService(
        uow_factory=uow_factory,
        adapter=None,
        config=DrawServiceConfig(gallery_capacity=10, gallery_page_size=50),
        data_dir=tmp_path / "data",
        model_names=["image-model"],
    )
    await service._clients["image-model"].aclose()
    client = httpx.AsyncClient(
        base_url=model.base_url, transport=httpx.MockTransport(handler)
    )
    service._clients["image-model"] = client
    service._client = client
    return service, engine


@pytest.mark.asyncio
async def test_reference_generation_uses_edits_multipart(tmp_path, monkeypatch) -> None:
    seen: list[httpx.Request] = []
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        bodies.append(request.content.decode("utf-8", errors="replace"))
        return _image_response()

    service, engine = await _make_service(tmp_path, monkeypatch, _Model(), handler)
    try:
        record = await service.generate_image(
            prompt="把参考图放到海滩日落场景",
            references=[_reference_file(service, tmp_path)],
            image_size="1024x1024",
        )
    finally:
        await service.close()
        await engine.dispose()

    assert record.image_id.startswith("tmp_")
    assert seen[0].url.path == "/v1/images/edits"
    assert seen[0].headers["content-type"].startswith("multipart/form-data")
    body = bodies[0]
    assert 'name="model"' in body and "gpt-image-2.5-flare" in body
    assert 'name="prompt"' in body and "海滩日落" in body
    assert 'name="size"' in body and "1024x1024" in body
    assert 'name="image"' in body
    assert "filename=\"reference_1.png\"" in body


@pytest.mark.asyncio
async def test_multiple_references_use_repeated_image_field(tmp_path, monkeypatch) -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode("utf-8", errors="replace"))
        return _image_response()

    service, engine = await _make_service(tmp_path, monkeypatch, _Model(), handler)
    try:
        await service.generate_image(
            prompt="融合两张参考图",
            references=[
                _reference_file(service, tmp_path, "ref1.png", "red"),
                _reference_file(service, tmp_path, "ref2.png", "green"),
            ],
        )
    finally:
        await service.close()
        await engine.dispose()

    assert bodies[0].count('name="image[]"') == 2
    assert "reference_1.png" in bodies[0] and "reference_2.png" in bodies[0]


@pytest.mark.asyncio
async def test_edits_failure_falls_back_to_generations(tmp_path, monkeypatch) -> None:
    paths: list[str] = []
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/images/edits":
            return httpx.Response(404, json={"error": {"message": "not found"}})
        import json as _json

        payloads.append(_json.loads(request.content.decode("utf-8")))
        return _image_response()

    service, engine = await _make_service(tmp_path, monkeypatch, _Model(), handler)
    try:
        record = await service.generate_image(
            prompt="参考图", references=[_reference_file(service, tmp_path)]
        )
    finally:
        await service.close()
        await engine.dispose()

    assert record.image_id.startswith("tmp_")
    assert paths == ["/v1/images/edits", "/v1/images/generations"]
    assert payloads[0]["image"].startswith("data:image/png;base64,")
    assert payloads[0]["model"] == "gpt-image-2.5-flare"


@pytest.mark.asyncio
async def test_image_api_generations_skips_edits(tmp_path, monkeypatch) -> None:
    paths: list[str] = []
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        paths.append(request.url.path)
        payloads.append(_json.loads(request.content.decode("utf-8")))
        return _image_response()

    model = _Model()
    model.settings.image_api = "generations"
    model.settings.image_reference_param = "image_urls"
    service, engine = await _make_service(tmp_path, monkeypatch, model, handler)
    try:
        await service.generate_image(
            prompt="参考图", references=[_reference_file(service, tmp_path)]
        )
    finally:
        await service.close()
        await engine.dispose()

    assert paths == ["/v1/images/generations"]
    assert payloads[0]["image_urls"][0].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_image_api_edits_does_not_fall_back(tmp_path, monkeypatch) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(400, json={"error": {"message": "image file is required"}})

    model = _Model()
    model.settings.image_api = "edits"
    service, engine = await _make_service(tmp_path, monkeypatch, model, handler)
    try:
        with pytest.raises(ImageGenerationError):
            await service.generate_image(
                prompt="参考图", references=[_reference_file(service, tmp_path)]
            )
    finally:
        await service.close()
        await engine.dispose()

    assert paths == ["/v1/images/edits"]


@pytest.mark.asyncio
async def test_text_to_image_still_uses_generations(tmp_path, monkeypatch) -> None:
    paths: list[str] = []
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        paths.append(request.url.path)
        payloads.append(_json.loads(request.content.decode("utf-8")))
        return _image_response()

    service, engine = await _make_service(tmp_path, monkeypatch, _Model(), handler)
    try:
        await service.generate_image(prompt="一只猫")
    finally:
        await service.close()
        await engine.dispose()

    assert paths == ["/v1/images/generations"]
    assert "image" not in payloads[0]
    assert payloads[0]["image_size"]
