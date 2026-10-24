"""官方插件的 pydantic 配置模型 -> 面板 schema。

旧实现按 json-schema 名字（"integer"/"boolean"）映射类型，而 pydantic 的注解
里根本没有这些字符串，于是 int/bool/float 全部退化成 str：面板把端口号渲染成
文本框、布尔渲染成字符串，保存时类型就漂了。类型必须来自注解本身。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.config_manager import (
    _type_name,
    describe_pydantic_model,
)
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
        dumped = json.dumps(
            describe_pydantic_model(model), ensure_ascii=False, default=str
        )
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
