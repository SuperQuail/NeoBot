"""spec(4) Part B：生图 payload 的实际下发（A20 生图侧 / A25）。

从真实 config.toml 注册生图模型（provider=DeepSeek），再抓取发往
/images/generations 的请求体：
- 自定义参数（extra_body）原样并入生图 payload；
- 生图 payload 不含 __deepseek_*__ 内部键（修掉 spec 2.5 的既有缺陷）。
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from neobot_app.config.loader.manager import Config
from neobot_app.config.model_params import clear_inferred
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.drawing.config import DrawServiceConfig
from neobot_app.drawing.service import CreatorImageService
from neobot_chat import get_model_registry
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

_DEEPSEEK_ENV = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test",
}

_CONFIG = (
    "[bot]\naccount = 10001\n\n[chat]\n\n"
    "[[models.registry]]\n"
    'key = "img-a"\n'
    'model_type = "image"\n'
    'description = "测试生图模型"\n'
    'provider = "DeepSeek"\n'
    'model_name = "stub-image-xl"\n'
    "[models.registry.settings]\n"
    "timeout_seconds = 30.0\n"
    "extra_body = { top_k = 40 }\n"
    "\n[agent.creator]\nenabled = true\n"
    "\n[models.assignments]\n"
    'creator_image_models = ["img-a"]\n'
)


@pytest.fixture(autouse=True)
def _clean_registry():
    get_model_registry().clear()
    clear_inferred()
    yield
    get_model_registry().clear()
    clear_inferred()


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def _image_response() -> httpx.Response:
    return httpx.Response(
        200, json={"data": [{"b64_json": base64.b64encode(_png_bytes()).decode()}]}
    )


async def _make_service(tmp_path: Path, model: Any, handler) -> tuple[CreatorImageService, Any]:
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'params-image.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    service = CreatorImageService(
        uow_factory=uow_factory,
        adapter=None,
        config=DrawServiceConfig(gallery_capacity=10, gallery_page_size=50),
        data_dir=tmp_path / "data",
        model_names=["img-a"],
    )
    await service._clients["img-a"].aclose()
    client = httpx.AsyncClient(
        base_url=str(getattr(model, "base_url", "http://model.invalid/v1")),
        transport=httpx.MockTransport(handler),
    )
    service._clients["img-a"] = client
    service._client = client
    return service, engine


async def test_custom_extra_body_reaches_image_payload_without_internal_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """A20（生图）+ A25：自定义参数进 payload，内部键不进 payload。"""
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    config_path = tmp_path / "bot.toml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    Config.load(config_path, BotConfig)

    # 生图服务以注册表里的模型为准（真实运行路径）
    monkeypatch.setattr(
        "neobot_app.drawing.service.get_registered_model",
        lambda name: get_model_registry().get(name),
    )
    model = get_model_registry().get("img-a")
    assert not any(str(key).startswith("__deepseek") for key in model.settings.extra_body)

    payloads: list[dict[str, Any]] = []
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        payloads.append(json.loads(request.content.decode("utf-8")))
        return _image_response()

    service, engine = await _make_service(tmp_path, model, handler)
    try:
        await service.generate_image(prompt="一只猫")
    finally:
        await service.close()
        await engine.dispose()

    assert paths == ["/images/generations"]
    assert payloads[0]["top_k"] == 40
    assert payloads[0]["model"] == "stub-image-xl"
    assert "prompt" in payloads[0]
    assert not any(str(key).startswith("__deepseek") for key in payloads[0])
