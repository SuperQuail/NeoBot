"""describe_dataclass 透传选项显示名与分组（模型库「推理强度」字段依赖）。

约定：option_labels / option_groups 只在 metadata 存在且形态合法时出现；
不带这些 metadata 的字段描述必须与改造前完全一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neobot_app.builtin_plugins.dashboard.config_parts.describe import describe_dataclass

#: 普通标量字段的固定键集合：多一个键都可能让旧字段在前端走错渲染分支。
_PLAIN_KEYS = {
    "name",
    "path",
    "label",
    "description",
    "required",
    "default",
    "value",
    "kind",
    "type",
    "readonly",
    "hot_reload",
    "restart_reason",
    "hidden",
}


@dataclass
class _Grouped:
    effort: str = field(
        default="",
        metadata={
            "options": ["", "low", "high", "claude:high"],
            "options_strict": True,
            "option_labels": {"low": "低", "high": "高", "claude:high": "Claude 系 · high"},
            "option_groups": [
                {"label": "OpenAI 系（reasoning_effort）", "options": ["", "low", "high"]},
                {"label": "Claude 系（output_config.effort）", "options": ["claude:high"]},
            ],
        },
    )
    plain: str = ""
    options_only: str = field(
        default="low",
        metadata={"options": ["low", "high"], "options_strict": True},
    )


@dataclass
class _Dirty:
    labels: str = field(default="", metadata={"option_labels": ["low", "高"]})
    groups: str = field(
        default="",
        metadata={"option_groups": {"label": "OpenAI 系", "options": ["low"]}},
    )
    mixed: str = field(
        default="",
        metadata={
            "option_groups": [
                "not-a-group",
                {"label": "缺 options"},
                {"label": 7, "options": ["low"]},
                {"label": "合法", "options": [1, "low"]},
            ]
        },
    )


def _by_name(schema: type) -> dict[str, dict]:
    return {item["name"]: item for item in describe_dataclass(schema, schema())}


def test_option_labels_and_groups_are_passed_through() -> None:
    effort = _by_name(_Grouped)["effort"]

    assert effort["options"] == ["", "low", "high", "claude:high"]
    assert effort["options_strict"] is True
    assert effort["option_labels"] == {"low": "低", "high": "高", "claude:high": "Claude 系 · high"}
    assert effort["option_groups"] == [
        {"label": "OpenAI 系（reasoning_effort）", "options": ["", "low", "high"]},
        {"label": "Claude 系（output_config.effort）", "options": ["claude:high"]},
    ]


def test_fields_without_option_metadata_keep_the_old_shape() -> None:
    fields = _by_name(_Grouped)

    assert set(fields["plain"]) == _PLAIN_KEYS
    assert set(fields["options_only"]) == _PLAIN_KEYS | {"options", "options_strict"}


def test_malformed_option_metadata_is_dropped() -> None:
    fields = _by_name(_Dirty)

    assert "option_labels" not in fields["labels"]
    assert "option_groups" not in fields["groups"]
    # 非法分组逐项跳过，合法分组保留；选项值统一转成字符串。
    assert fields["mixed"]["option_groups"] == [{"label": "合法", "options": ["1", "low"]}]
