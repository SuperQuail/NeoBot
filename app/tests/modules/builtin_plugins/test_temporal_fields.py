"""时间类配置字段：kind 映射与 ISO 8601 取值契约。

守住三件事：
1. dataclass（本体）与 pydantic（插件）两条描述路径都给出 date / time / datetime 三种 kind；
2. 下发给前端的值一律是 ISO 8601 字符串（``datetime`` 用 ``T`` 分隔，不能用 ``str()`` 的空格形态）；
3. 面板回传的 ISO 字符串能被转换回 Python 对象，清空的 optional 字段回落到 None。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

import pytest
from pydantic import BaseModel

from neobot_app.builtin_plugins.dashboard.config_parts.describe import (
    describe_dataclass,
    describe_pydantic_model,
)
from neobot_app.builtin_plugins.dashboard.config_parts.schema import (
    _coerce_payload,
    _jsonable,
    _validate_type,
)


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
    assert descriptors[name]["type"] == kind


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
    assert descriptors[name]["type"] == kind


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
