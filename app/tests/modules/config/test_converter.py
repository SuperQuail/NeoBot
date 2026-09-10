"""converter 模块（TOML→dataclass 转换、类型/枚举/范围校验）测试。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List

import pytest

from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass
from neobot_app.config.schemas.bot import (
    Chat,
    DeepSeekModelSettings,
    Models,
)


@dataclass
class _SubConfig:
    name: str = "sub-default"
    count: int = 1


@dataclass
class _RootConfig:
    title: str = "title-default"
    amount: int = 3
    ratio: float = 0.5
    flag: bool = True
    off_flag: bool = False
    items: List[str] = field(default_factory=lambda: ["a", "b"])
    sub: _SubConfig = field(default_factory=_SubConfig)


@dataclass
class _RequiredFieldConfig:
    required_value: str


class _Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass
class _EnumConfig:
    color: _Color = _Color.RED


def test_dict_to_dataclass_converts_scalar_types():
    """字符串/数值等原始值必须按字段类型转换为 int/float/str/bool 并保留列表结构。"""
    # Arrange
    raw = {
        "title": 123,
        "amount": "7",
        "ratio": "0.25",
        "flag": "on",
        "items": ["x", "y"],
    }

    # Act
    result = dict_to_dataclass(raw, _RootConfig)

    # Assert
    assert result.title == "123"
    assert result.amount == 7
    assert result.ratio == 0.25
    assert result.flag is True
    assert result.items == ["x", "y"]
    assert result.sub == _SubConfig()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("enabled", True),
        ("enable", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("disabled", False),
        ("unable", False),
    ],
)
def test_dict_to_dataclass_bool_conversion_from_string(raw, expected):
    """布尔字符串（true/1/yes/on 与 false/0/no/off 等）必须正确转换为对应布尔值。"""
    # Arrange / Act
    result = dict_to_dataclass({"flag": raw}, _RootConfig)

    # Assert
    assert result.flag is expected


def test_dict_to_dataclass_invalid_value_falls_back_to_default():
    """无法转换的非法值（非数字字符串）必须回退为字段默认值且不抛异常。"""
    # Arrange
    raw = {"amount": "abc", "ratio": "1.5xyz"}

    # Act
    result = dict_to_dataclass(raw, _RootConfig)

    # Assert
    assert result.amount == 3
    assert result.ratio == 0.5


def test_dict_to_dataclass_bool_from_arbitrary_int_is_clamped():
    """非 0/1 的 int 值写入 bool 字段必须钳位为 True/False（2→True、-1→False）且不抛异常。"""
    # Arrange
    raw = {"off_flag": 2}

    # Act
    result = dict_to_dataclass(raw, _RootConfig)

    # Assert
    assert result.off_flag is True


def test_dict_to_dataclass_enum_member_passthrough_and_string_fallback():
    """枚举成员必须原样通过；字符串值无法转换时必须回退默认值且不抛异常。"""
    # Arrange
    raw_member = {"color": _Color.BLUE}
    raw_string = {"color": "blue"}

    # Act
    result_member = dict_to_dataclass(raw_member, _EnumConfig)
    result_string = dict_to_dataclass(raw_string, _EnumConfig)

    # Assert
    assert result_member.color is _Color.BLUE
    assert result_string.color is _Color.RED


def test_dict_to_dataclass_probability_out_of_range_passes_through():
    """deepseek_random_thinking_probability 越界值在 converter 层原样保留，范围裁剪由 manager 层负责。"""
    # Arrange
    raw_high = {"deepseek_random_thinking_probability": 2.5}
    raw_negative = {"deepseek_random_thinking_probability": -0.5}

    # Act
    result_high = dict_to_dataclass(raw_high, DeepSeekModelSettings)
    result_negative = dict_to_dataclass(raw_negative, DeepSeekModelSettings)

    # Assert
    assert result_high.deepseek_random_thinking_probability == 2.5
    assert result_negative.deepseek_random_thinking_probability == -0.5


def test_dict_to_dataclass_group_chat_chance_clamped_to_range():
    """群聊回复概率超出 0~1 范围必须钳位到边界（5.0→1.0），不得原样保留。"""
    # Arrange
    raw = {"group_chat_chance": 5.0}

    # Act
    result = dict_to_dataclass(raw, Chat)

    # Assert
    assert result.group_chat_chance == 1.0


def test_dict_to_dataclass_nested_structure_and_subclass_detection():
    """嵌套 dataclass 必须递归转换，且通过默认值自动识别 DeepSeekModelSettings 子类。"""
    # Arrange
    raw = {
        "registry": [
            {
                "key": "deepseek-v4-pro",
                "provider": "DeepSeek",
                "model_name": "deepseek-chat",
                "settings": {
                    "deepseek_thinking_mode": "random",
                    "deepseek_reasoning_effort": "max",
                },
            }
        ]
    }

    # Act
    models = dict_to_dataclass(raw, Models)

    # Assert
    primary = models.get("deepseek-v4-pro")
    assert primary is not None
    assert primary.provider == "DeepSeek"
    assert primary.model_name == "deepseek-chat"
    assert isinstance(primary.settings, DeepSeekModelSettings)
    assert primary.settings.deepseek_thinking_mode == "random"
    assert primary.settings.deepseek_reasoning_effort == "max"
    assert primary.pricing.input_price_per_mtokens == 0.0
    # 调用方只引用 key，未在 registry 里出现的默认条目不应被隐式保留
    assert models.assignments.primary_chat_model == "deepseek-v4-pro"
    assert [item.key for item in models.registry] == ["deepseek-v4-pro"]


def test_dataclass_to_toml_fills_defaults_and_marks_required_missing():
    """dataclass_to_toml 必须写入默认值；无现有值时标量字段报缺失，无默认的必需字段必须列入缺失清单。"""
    # Arrange / Act
    root_doc, root_required, root_optional = dataclass_to_toml(
        _RootConfig, None, is_root=True
    )
    full_doc, full_required, full_optional = dataclass_to_toml(
        _RootConfig,
        {
            "title": "t",
            "amount": 9,
            "ratio": 0.9,
            "flag": False,
            "off_flag": True,
            "items": ["x"],
            "sub": {"name": "s", "count": 5},
        },
        is_root=True,
    )
    required_doc, required, optional = dataclass_to_toml(
        _RequiredFieldConfig, None, is_root=True
    )

    # Assert
    # 无现有数据时：非 Optional 标量字段（即使有默认值）按当前语义报缺失（嵌套内标量同样传播）
    assert root_required == [
        "title",
        "amount",
        "ratio",
        "flag",
        "off_flag",
        "items",
        "sub.name",
        "sub.count",
    ]
    assert root_optional == []
    # 有完整现有数据时无任何缺失，现有值不被默认值覆盖
    assert full_required == []
    assert full_optional == []
    assert full_doc.unwrap()["amount"] == 9
    assert full_doc.unwrap()["sub"]["name"] == "s"
    # 无默认值的必需字段必须列入缺失
    assert required == ["required_value"]
    assert optional == []
    assert required_doc.unwrap()["required_value"] == ""


def test_dict_to_dataclass_uses_alias_metadata():
    """字段 metadata 中配置的别名键必须能被识别并正确转换。"""
    # Arrange
    raw = {"group_Response_coefficient": {"111111": 0.8}}

    # Act
    result = dict_to_dataclass(raw, Chat)

    # Assert
    assert result.group_response_coefficient == {"111111": 0.8}
