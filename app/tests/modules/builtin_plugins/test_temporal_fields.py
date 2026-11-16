"""时间类配置字段：kind 映射与 ISO 8601 取值契约。

守住三件事：
1. dataclass（本体）与 pydantic（插件）两条描述路径都给出 date / time / datetime 三种 kind；
2. 下发给前端的值一律是 ISO 8601 字符串（``datetime`` 用 ``T`` 分隔，不能用 ``str()`` 的空格形态）；
3. 面板回传的 ISO 字符串能被转换回 Python 对象，清空的 optional 字段回落到 None。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Annotated, Optional

import pytest
import tomlkit
from pydantic import BaseModel, Field

from neobot_app.builtin_plugins.dashboard.config_parts.describe import (
    describe_dataclass,
    describe_pydantic_model,
)
from neobot_app.builtin_plugins.dashboard.config_parts.schema import (
    _coerce_payload,
    _validate_payload,
    _jsonable,
    _type_name,
    _validate_type,
)
from neobot_app.builtin_plugins.dashboard.config_parts.toml import (
    _diff_document,
    _merge_into_document,
)
from neobot_app.builtin_plugins.dashboard.plugin_config import PluginConfigEditor


@dataclass
class _BotSettings:
    run_at: datetime = field(default_factory=lambda: datetime(2026, 11, 16, 23, 39, 55))
    run_on: date = field(default_factory=lambda: date(2026, 11, 16))
    window: time = field(default_factory=lambda: time(23, 39, 55))
    optional_at: Optional[datetime] = None


class _PluginSettings(BaseModel):
    run_at: datetime
    run_on: date
    window: time
    optional_at: Optional[datetime] = None


@pytest.mark.parametrize(
    ("name", "kind"),
    [("run_at", "datetime"), ("run_on", "date"), ("window", "time")],
)
def test_dataclass_fields_become_temporal_kinds(name: str, kind: str) -> None:
    descriptors = {item["name"]: item for item in describe_dataclass(_BotSettings, _BotSettings())}

    assert descriptors[name]["kind"] == kind


@pytest.mark.parametrize(
    ("name", "kind"),
    [("run_at", "datetime"), ("run_on", "date"), ("window", "time")],
)
def test_pydantic_fields_become_temporal_kinds(name: str, kind: str) -> None:
    values = {
        "run_at": datetime(2026, 11, 16, 23, 39, 55),
        "run_on": date(2026, 11, 16),
        "window": time(23, 39, 55),
    }
    descriptors = {item["name"]: item for item in describe_pydantic_model(_PluginSettings, values)}

    assert descriptors[name]["kind"] == kind


def test_values_are_iso_8601_strings() -> None:
    descriptors = {item["name"]: item for item in describe_dataclass(_BotSettings, _BotSettings())}

    assert descriptors["run_at"]["value"] == "2026-11-16T23:39:55"
    assert descriptors["run_on"]["value"] == "2026-11-16"
    assert descriptors["window"]["value"] == "23:39:55"


def test_optional_field_without_value_stays_none() -> None:
    descriptors = {item["name"]: item for item in describe_dataclass(_BotSettings, _BotSettings())}

    assert descriptors["optional_at"]["value"] is None
    assert descriptors["optional_at"]["required"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 11, 16, 23, 39, 55), "2026-11-16T23:39:55"),
        (date(2026, 11, 16), "2026-11-16"),
        (time(23, 39, 55), "23:39:55"),
    ],
)
def test_jsonable_uses_isoformat(value: object, expected: str) -> None:
    """``str(datetime)`` 用空格分隔，不是 ISO 8601 —— 必须走 isoformat()。"""
    assert _jsonable(value) == expected


def test_payload_coercion_parses_iso_strings() -> None:
    coerced = _coerce_payload(
        _BotSettings,
        {
            "run_at": "2026-11-16T23:39:55",
            "run_on": "2026-11-16",
            "window": "23:39:55",
            "optional_at": "",
        },
    )

    assert coerced["run_at"] == datetime(2026, 11, 16, 23, 39, 55)
    assert coerced["run_on"] == date(2026, 11, 16)
    assert coerced["window"] == time(23, 39, 55)
    # 控件清空 → 空串 → 不设置
    assert coerced["optional_at"] is None


@pytest.mark.parametrize(
    ("raw", "target", "expected"),
    [
        ("2026-11-16T23:39:55", datetime, datetime(2026, 11, 16, 23, 39, 55)),
        ("2026-11-16 23:39:55", datetime, datetime(2026, 11, 16, 23, 39, 55)),
        ("2026-11-16", date, date(2026, 11, 16)),
        ("23:39:55", time, time(23, 39, 55)),
    ],
)
def test_validate_type_parses_iso(raw: str, target: type, expected: object) -> None:
    valid, converted = _validate_type(raw, target)

    assert valid is True
    assert converted == expected


def test_invalid_temporal_string_is_rejected() -> None:
    valid, converted = _validate_type("不是时间", datetime)

    assert valid is False
    assert converted == "不是时间"


# ---------------------------------------------------------------------------
# 保存路径：可选字段清空（null）必须真的从文件里消失
# ---------------------------------------------------------------------------


def test_dataclass_save_with_null_removes_existing_key() -> None:
    """面板回传 null = 不设置：文件里已有的旧值要删掉，否则读回仍是旧值。"""
    document = tomlkit.parse("[task]\nrun_at = 2026-11-16T23:39:55\nother = 1\n")

    diff = _diff_document({"run_at": "2026-11-16T23:39:55"}, {"run_at": None})
    assert diff == {"run_at": None}

    _merge_into_document(document["task"], diff)

    assert "run_at" not in document["task"]
    assert document["task"]["other"] == 1


def test_plugin_save_with_null_removes_existing_key(tmp_path) -> None:
    """插件配置同一语义：不能抛 ConvertError，也不能把旧值留在文件里。"""
    path = tmp_path / "config.toml"
    path.write_text('run_at = 2026-11-16T23:39:55\nname = "x"\n', encoding="utf-8")
    editor = PluginConfigEditor(path, defaults={"run_at": None, "name": "x"})

    editor.save(config={"run_at": None, "name": "x"})

    written = path.read_text(encoding="utf-8")
    assert "run_at" not in written
    assert editor.read()["config"]["run_at"] is None


def test_plugin_save_nested_null_is_dropped(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[task]\nrun_at = 2026-11-16T23:39:55\nkeep = 1\n", encoding="utf-8")
    editor = PluginConfigEditor(path, defaults={"task": {"run_at": None, "keep": 1}})

    editor.save(config={"task": {"run_at": None, "keep": 1}})

    written = path.read_text(encoding="utf-8")
    assert "run_at" not in written
    assert "keep = 1" in written


# ---------------------------------------------------------------------------
# Annotated 包装：插件作者最常见的写法不能静默退化成 JSON
# ---------------------------------------------------------------------------


class _AnnotatedPlugin(BaseModel):
    wrapped: Optional[Annotated[datetime, Field(description="带 Field 的可选时间")]] = None
    required_wrapped: Annotated[datetime, Field(description="必填时间")]


def test_annotated_optional_datetime_keeps_temporal_kind() -> None:
    descriptors = {item["name"]: item for item in describe_pydantic_model(_AnnotatedPlugin, {})}

    assert descriptors["wrapped"]["kind"] == "datetime"
    assert descriptors["required_wrapped"]["kind"] == "datetime"


@pytest.mark.parametrize(
    "annotation",
    [datetime, Optional[datetime], Annotated[datetime, "meta"]],
)
def test_type_name_unwraps_annotated(annotation: object) -> None:
    assert _type_name(annotation) == "datetime"


def test_clearing_required_temporal_field_reports_readable_error() -> None:
    """必填时间字段被清空时，报「不能清空」而不是「实际为 NoneType」。"""
    errors: list[dict[str, str]] = []

    _validate_payload(_BotSettings, {"run_at": None, "run_on": "2026-11-16", "window": "23:39:55"}, "", errors)

    assert any("必填" in item["message"] for item in errors)


def test_plugin_save_drops_null_inside_object_list(tmp_path) -> None:
    """list[Model] 的某一行清空可选字段时，不能把 None 喂给 tomlkit。"""
    path = tmp_path / "config.toml"
    path.write_text('keep = 1\n\n[[rows]]\nat = 2026-11-16T23:39:55\nnote = "x"\n', encoding="utf-8")
    editor = PluginConfigEditor(path, defaults={"keep": 1, "rows": []})

    editor.save(config={"keep": 1, "rows": [{"at": None, "note": "x"}]})

    written = path.read_text(encoding="utf-8")
    assert "at =" not in written
    assert 'note = "x"' in written
