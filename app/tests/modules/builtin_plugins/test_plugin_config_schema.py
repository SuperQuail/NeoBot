"""官方插件的 pydantic 配置模型 -> 面板 schema。

旧实现按 json-schema 名字（"integer"/"boolean"）映射类型，而 pydantic 的注解
里根本没有这些字符串，于是 int/bool/float 全部退化成 str：面板把端口号渲染成
文本框、布尔渲染成字符串，保存时类型就漂了。类型必须来自注解本身。
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.config_manager import (
    _type_name,
    describe_pydantic_model,
)
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER
from neobot_app.builtin_plugins.minigame.config import ALL_GAME_IDS, MinigameConfig
from neobot_app.builtin_plugins.starship.config import StarshipConfig
from neobot_app.builtin_plugins.streaming_parser.config import StreamConfig

OFFICIAL_MODELS = (DashboardConfig, MinigameConfig, StarshipConfig, StreamConfig)


def _fields(model: Any, values: Any = None) -> dict[str, dict]:
    return {item["name"]: item for item in describe_pydantic_model(model, values)}


def test_scalar_types_come_from_annotation() -> None:
    assert _fields(DashboardConfig)["port"]["type"] == "int"
    assert _fields(DashboardConfig)["manage_plugins"]["type"] == "bool"
    assert _fields(StreamConfig)["request_timeout"]["type"] == "float"
    assert _fields(StreamConfig)["poll_interval_seconds"]["type"] == "int"


def test_list_field_gets_kind_and_element_type() -> None:
    field = _fields(MinigameConfig)["enabled_games"]

    assert field["type"] == "list"
    assert field["kind"] == "list"
    assert field["element_type"] == "str"
    assert field["default"] == list(ALL_GAME_IDS)


def test_defaults_never_leak_pydantic_undefined() -> None:
    for model in OFFICIAL_MODELS:
        dumped = json.dumps(describe_pydantic_model(model), ensure_ascii=False, default=str)
        assert "PydanticUndefined" not in dumped, model.__name__


def test_pep604_and_typing_optional_both_resolve_to_int() -> None:
    class Model(BaseModel):
        plain: int | None = None
        classic: Optional[int] = None

    fields = _fields(Model)

    assert fields["plain"]["type"] == "int"
    assert fields["classic"]["type"] == "int"
    assert _type_name(int | None) == "int"
    assert _type_name(Optional[int]) == "int"


def test_model_secret_defaults_do_not_reenter_response_schema() -> None:
    """模型描述覆盖编辑器 schema 时，默认密钥仍只能表示是否已设置。"""

    class CookieConfig(BaseModel):
        cookie: str = "synthetic-model-cookie"
        api_key: str = "synthetic-model-api-key"
        interval: int = 60

    fields = _fields(CookieConfig, {"cookie": "synthetic-stored-cookie"})
    serialized = json.dumps(fields, ensure_ascii=False)

    for secret in ("synthetic-model-cookie", "synthetic-model-api-key", "synthetic-stored-cookie"):
        assert secret not in serialized
    for name in ("cookie", "api_key"):
        assert fields[name]["sensitive"] is True
        assert fields[name]["has_value"] is True
        assert fields[name]["default"] == ""
        assert fields[name]["value"] == ""
    assert fields["interval"]["default"] == 60


@pytest.mark.parametrize("use_values", [False, True])
def test_nested_model_secrets_stay_structured_and_masked(use_values: bool) -> None:
    """嵌套模型必须先展开再脱敏，不能退化成包含密钥的字符串。"""

    class Account(BaseModel):
        cookie: str = "synthetic-nested-default-cookie"
        username: str = "bot"

    class PluginConfig(BaseModel):
        service: Account = Field(default_factory=Account)
        accounts: list[Account] = Field(default_factory=lambda: [Account(cookie="synthetic-list-default-cookie")])

    values = (
        {
            "service": Account(cookie="synthetic-nested-value-cookie"),
            "accounts": [Account(cookie="synthetic-list-value-cookie")],
        }
        if use_values
        else None
    )
    fields = _fields(PluginConfig, values)
    serialized = json.dumps(fields, ensure_ascii=False)

    for secret in (
        "synthetic-nested-default-cookie",
        "synthetic-list-default-cookie",
        "synthetic-nested-value-cookie",
        "synthetic-list-value-cookie",
    ):
        assert secret not in serialized
    masked_account = {"cookie": SECRET_PLACEHOLDER, "username": "bot"}
    assert fields["service"]["default"] == masked_account
    assert fields["service"]["value"] == masked_account
    assert fields["accounts"]["default"] == [masked_account]
    assert fields["accounts"]["value"] == [masked_account]
