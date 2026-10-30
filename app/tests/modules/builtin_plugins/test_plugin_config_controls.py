"""常用插件配置声明直接接入宿主控件，并保留嵌套值和凭据边界。"""

import json
from enum import Enum, IntEnum
from typing import Literal

import pytest
from pydantic import BaseModel, Field, SecretBytes, SecretStr

from neobot_app.builtin_plugins.dashboard.config_parts.describe import describe_pydantic_model
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER


def fields(model, values=None):
    return {field["name"]: field for field in describe_pydantic_model(model, values)}


class Priority(IntEnum):
    normal = 1
    urgent = 2


class Style(Enum):
    compact = "compact"
    expanded = "expanded"


def test_literal_and_enum_choices_keep_original_values_and_labels():
    class Config(BaseModel):
        delivery: Literal["instant", "digest"] = Field(
            default="instant", title="通知方式", json_schema_extra={"option_labels": {"digest": "汇总通知"}}
        )
        priority: Priority = Priority.normal
        style: Style = Style.compact
        decision: Literal[True, False] = True

    described = fields(Config)
    assert described["delivery"]["options"] == ["instant", "digest"]
    assert described["delivery"]["options_strict"] is True
    assert described["delivery"]["option_labels"] == {"digest": "汇总通知"}
    assert described["delivery"]["label"] == "通知方式"
    assert described["priority"]["option_values"] == {"1": 1, "2": 2}
    assert described["priority"]["value"] == described["priority"]["default"] == 1
    assert described["style"]["value"] == "compact"
    assert described["decision"]["option_values"] == {"true": True, "false": False}


def test_nested_model_becomes_fields_with_real_paths_and_metadata():
    class Connection(BaseModel):
        host: str = Field(default="localhost", title="服务地址", description="填写服务主机。")
        timeout: int = Field(default=10, ge=1, le=120, title="超时（秒）")
        identity: str = Field(default="service", frozen=True)

    class Config(BaseModel):
        connection: Connection = Field(default_factory=Connection, title="连接设置")

    group = fields(Config, {"connection": {"host": "example.test", "timeout": 30}})["connection"]
    assert group["kind"] == "group"
    assert group["label"] == "连接设置"
    nested = {field["name"]: field for field in group["fields"]}
    assert nested["host"]["path"] == ["connection", "host"]
    assert nested["host"]["value"] == "example.test"
    assert nested["host"]["label"] == "服务地址"
    assert nested["host"]["description"] == "填写服务主机。"
    assert nested["timeout"]["value"] == 30
    assert nested["timeout"]["min"] == 1
    assert nested["timeout"]["max"] == 120
    assert nested["identity"]["readonly"] is True


def test_model_list_has_add_template_and_indexed_fields_without_secret_defaults():
    class Connection(BaseModel):
        name: str = "默认连接"
        key: SecretStr = SecretStr("synthetic-default-private")

    class Config(BaseModel):
        routes: list[Connection] = Field(default_factory=lambda: [Connection()])

    group = fields(Config, {"routes": [{"name": "第一条", "key": "synthetic-stored-private"}]})["routes"]
    assert group["kind"] == "model_list"
    assert group["value"] == [{"name": "第一条", "key": SECRET_PLACEHOLDER}]
    template = {field["name"]: field for field in group["item_fields"]}
    actual = {field["name"]: field for field in group["items"][0]["fields"]}
    assert template["name"]["default"] == "默认连接"
    assert actual["name"]["path"] == ["routes", "0", "name"]
    assert actual["name"]["value"] == "第一条"
    assert template["key"]["value"] == actual["key"]["value"] == ""
    assert template["key"]["sensitive"] is actual["key"]["sensitive"] is True
    assert actual["key"]["has_value"] is True
    assert "synthetic-" not in json.dumps(group)


def test_dictionary_and_scalar_list_select_existing_collection_controls():
    class Config(BaseModel):
        weights: dict[str, int] = Field(default_factory=lambda: {"primary": 1})
        tags: list[str] = Field(default_factory=lambda: ["第一组"])

    described = fields(Config)
    assert described["weights"]["kind"] == "dict"
    assert described["weights"]["type"] == "dict"
    assert described["weights"]["value"] == {"primary": 1}
    assert described["tags"]["kind"] == "list"
    assert described["tags"]["element_type"] == "str"


@pytest.mark.parametrize("secret_type", [SecretStr, SecretBytes])
@pytest.mark.parametrize("populated", [False, True])
def test_secret_types_are_password_controls_with_correct_presence(secret_type, populated):
    value = "synthetic-secret-value" if populated else ""
    secret = secret_type(value.encode() if secret_type is SecretBytes else value)

    class Config(BaseModel):
        credential: secret_type = secret

    for values in (None, Config().model_dump()):
        descriptor = fields(Config, values)["credential"]
        assert descriptor["kind"] == "scalar"
        assert descriptor["type"] == "str"
        assert descriptor["sensitive"] is True
        assert descriptor["has_value"] is populated
        assert descriptor["value"] == descriptor["default"] == ""
        assert value == "" or value not in json.dumps(descriptor)


def test_private_container_stays_one_password_field_and_never_exposes_keys():
    class Config(BaseModel):
        vault: dict[str, str] = Field(
            default_factory=lambda: {"synthetic-private-key": "synthetic-private-value"},
            json_schema_extra={"writeOnly": True},
        )

    descriptor = fields(Config)["vault"]
    assert descriptor["kind"] == "scalar"
    assert descriptor["type"] == "str"
    assert descriptor["value"] == descriptor["default"] == ""
    assert descriptor["has_value"] is True
    assert "synthetic-private" not in json.dumps(descriptor)


def test_recursive_and_union_structures_keep_json_instead_of_lossy_text():
    class Node(BaseModel):
        name: str = "节点"
        child: "Node | None" = None

    class Config(BaseModel):
        tree: Node = Field(default_factory=Node)
        union: str | int = "default"
        nested_lists: list[list[int]] = Field(default_factory=list)
        collisions: Literal[1, "1"] = 1

    described = fields(Config)
    child = {field["name"]: field for field in described["tree"]["fields"]}["child"]
    assert child["kind"] == "json"
    assert child["value"] is None
    assert described["union"]["kind"] == "json"
    assert described["nested_lists"]["kind"] == "json"
    assert described["collisions"]["kind"] == "json"


def test_optional_scalar_types_stay_typed_and_unknown_structures_are_lossless():
    class Config(BaseModel):
        interval: int | None = None
        arbitrary: tuple[int, str] = (1, "one")

    described = fields(Config)
    assert described["interval"]["kind"] == "scalar"
    assert described["interval"]["type"] == "int"
    assert described["arbitrary"]["kind"] == "json"
    assert described["arbitrary"]["value"] == [1, "one"]


def test_text_hints_cannot_override_fixed_types_or_secret_controls():
    class Config(BaseModel):
        endpoint: str = Field(
            default="",
            json_schema_extra={"single_line": True, "placeholder": "填写服务地址", "kind": "html"},
        )
        retries: int = Field(default=3, json_schema_extra={"single_line": True, "placeholder": "不适用"})
        credential: SecretStr = Field(
            default=SecretStr("synthetic-private"),
            json_schema_extra={"single_line": False, "placeholder": "不得公开"},
        )

    described = fields(Config)
    assert described["endpoint"]["single_line"] is True
    assert described["endpoint"]["placeholder"] == "填写服务地址"
    assert described["endpoint"]["kind"] == "scalar"
    assert described["retries"]["type"] == "int"
    assert "single_line" not in described["retries"]
    assert "placeholder" not in described["retries"]
    assert described["credential"]["sensitive"] is True
    assert described["credential"]["value"] == ""
    assert "single_line" not in described["credential"]
