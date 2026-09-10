"""生图多模型：选择解析与绘图技能参数。"""

from __future__ import annotations

import pytest

from neobot_app.drawing.service import CreatorImageService
from neobot_chat import ModelPricing, ModelSettings, RegisteredModel, register_model


def _make_service(names: list[str]) -> CreatorImageService:
    service = object.__new__(CreatorImageService)
    service._model_names = tuple(names)
    service._default_model_name = names[0]
    service._models = {}
    for index, name in enumerate(names):
        service._models[name] = RegisteredModel(
            name=name,
            description=f"模型{index}",
            provider_name=f"Provider{index}",
            model_name=f"vendor/model-{index}",
            base_url="https://example.com",
            api_key="sk-test",
            pricing=ModelPricing(),
            settings=ModelSettings(),
        )
    return service


def test_resolve_model_name_by_index_and_alias() -> None:
    service = _make_service(["creator_image_models_0", "creator_image_models_1"])

    assert service.resolve_model_name(None) == "creator_image_models_0"
    assert service.resolve_model_name("") == "creator_image_models_0"
    assert service.resolve_model_name("1") == "creator_image_models_1"
    assert service.resolve_model_name("Provider1") == "creator_image_models_1"
    assert service.resolve_model_name("vendor/model-1") == "creator_image_models_1"
    assert service.resolve_model_name("模型0") == "creator_image_models_0"


def test_resolve_model_name_rejects_unknown() -> None:
    service = _make_service(["creator_image_models_0"])

    with pytest.raises(ValueError):
        service.resolve_model_name("不存在")


def test_available_models_lists_default() -> None:
    service = _make_service(["creator_image_models_0", "creator_image_models_1"])

    models = service.available_models()

    assert [item["index"] for item in models] == [0, 1]
    assert models[0]["default"] is True
    assert models[1]["default"] is False
    assert models[1]["provider"] == "Provider1"


def test_register_model_accepts_second_image_model() -> None:
    register_model(
        RegisteredModel(
            name="creator_image_models_1",
            description="备用生图模型",
            provider_name="SiliconFlow",
            model_name="black-forest-labs/FLUX.1-dev",
            base_url="https://api.siliconflow.cn/v1",
            api_key="sk-x",
            pricing=ModelPricing(),
            settings=ModelSettings(),
        ),
        replace=True,
    )
    from neobot_chat import get_registered_model

    assert get_registered_model("creator_image_models_1").description == "备用生图模型"
