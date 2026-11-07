"""入站模型解析的行为锁定：成功路径、输入边界与容错路径。

`parse.py` 的容错解析是上游字段变化时的最后一道兼容；失败后保留哪些字段、
哪些回默认值，都属于可观测行为，不能随重构漂移。
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from neobot_adapter.model.notice import GroupPoke
from neobot_adapter.utils.parse import safe_parse_model


class Inner(BaseModel):
    name: str = ""
    count: int = 0


class Outer(BaseModel):
    label: str = ""
    inner: Inner | None = None
    tags: list[int] = []


def test_valid_dict_parses() -> None:
    parsed = safe_parse_model({"label": "x", "inner": {"name": "n", "count": 2}, "tags": [1, 2]}, Outer)
    assert parsed == Outer(label="x", inner=Inner(name="n", count=2), tags=[1, 2])


def test_json_string_parses() -> None:
    assert safe_parse_model(json.dumps({"label": "x"}), Outer).label == "x"


def test_non_dict_and_bad_json_return_default_model() -> None:
    assert safe_parse_model(None, Outer) == Outer()
    assert safe_parse_model(123, Outer) == Outer()
    assert safe_parse_model("{not json", Outer) == Outer()


def test_validation_failure_keeps_tolerantly_parsable_fields() -> None:
    parsed = safe_parse_model({"post_type": "bogus", "group_id": 42, "sub_type": "poke"}, GroupPoke)
    dumped = parsed.model_dump(mode="json")
    assert dumped["post_type"] is None
    assert dumped["group_id"] == 42
    assert dumped["sub_type"] == "poke"


def test_tolerant_parse_drops_field_that_fails_to_convert() -> None:
    parsed = safe_parse_model({"label": "x", "inner": {"name": "n", "count": "oops"}}, Outer)
    assert parsed == Outer(label="x")


def test_nested_model_with_non_dict_value_falls_back() -> None:
    assert safe_parse_model({"label": "x", "inner": "oops"}, Outer) == Outer(label="x")


def test_list_field_conversion_failure_falls_back_to_default_model() -> None:
    assert safe_parse_model({"tags": ["1", "x", 2]}, Outer) == Outer()
