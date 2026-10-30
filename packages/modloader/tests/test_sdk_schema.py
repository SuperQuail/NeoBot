"""验证公开契约的配置类型与敏感默认值边界。"""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel, SecretStr

from neobot_modloader.sdk.schema import export_model_schema, schema_field_paths


class LoginConfig(BaseModel):
    cookie: str = "SESSDATA=synthetic-sdk-value"
    credential: str = Field(
        default="synthetic-hidden-value",
        examples=["synthetic-example-value"],
        json_schema_extra={"x-neobot": {"secret": True}},
    )
    username: str = "demo"


class ExampleConfig(BaseModel):
    login: LoginConfig = LoginConfig()
    access_key: SecretStr = SecretStr("synthetic-access-value")
    token_limit: int = Field(default=128, ge=1, le=2048)
    mode: Literal["quiet", "normal"] = "normal"


def test_export_preserves_types_and_removes_all_sensitive_defaults() -> None:
    schema = export_model_schema(ExampleConfig)
    assert schema is not None
    assert schema["properties"]["token_limit"]["type"] == "integer"
    assert schema["properties"]["token_limit"]["default"] == 128
    assert schema["properties"]["mode"]["enum"] == ["quiet", "normal"]
    assert schema["properties"]["login"]["default"] == {"username": "demo"}
    login = schema["$defs"]["LoginConfig"]["properties"]
    assert login["cookie"]["writeOnly"] is True
    assert "default" not in login["cookie"]
    assert "default" not in login["credential"]
    assert "examples" not in login["credential"]
    assert "default" not in schema["properties"]["access_key"]
    assert "synthetic" not in str(schema)


def test_export_never_runs_default_factory() -> None:
    calls = []

    def create_value() -> str:
        calls.append(True)
        return "created"

    class Config(BaseModel):
        value: str = Field(default_factory=create_value)

    export_model_schema(Config)
    assert calls == []


def test_export_does_not_mutate_model_schema() -> None:
    original = {
        "type": "object",
        "properties": {"session": {"type": "string", "writeOnly": True, "default": "hidden"}},
    }
    before = deepcopy(original)

    class Model:
        @classmethod
        def model_json_schema(cls, **_kwargs):
            return original

    assert "hidden" not in str(export_model_schema(Model))
    assert original == before


def test_schema_paths_resolve_nested_refs_without_looping() -> None:
    class Node(BaseModel):
        name: str
        child: "Node | None" = None

    paths = schema_field_paths(export_model_schema(Node))
    assert {"name", "child"} <= paths
    assert len(paths) < 20
    assert {"login", "login.username", "login.cookie", "mode"} <= schema_field_paths(export_model_schema(ExampleConfig))


def test_schema_none_is_supported_for_plugins_without_config() -> None:
    assert export_model_schema(None) is None
    assert schema_field_paths(None) == set()


def test_dictionary_and_tuple_defaults_follow_their_value_schemas() -> None:
    class Credential(BaseModel):
        value: str = Field(default="synthetic-dict-hidden", json_schema_extra={"x-neobot": {"secret": True}})
        label: str = "公开名称"

    class Config(BaseModel):
        accounts: dict[str, Credential] = {"primary": Credential()}
        pair: tuple[str, Credential] = ("公开说明", Credential())

    schema = export_model_schema(Config)
    assert schema["properties"]["accounts"]["default"] == {"primary": {"label": "公开名称"}}
    assert schema["properties"]["pair"]["default"] == ["公开说明", {"label": "公开名称"}]
    assert "synthetic-dict-hidden" not in str(schema)


def test_sensitive_root_and_tuple_slot_do_not_publish_or_shift_defaults() -> None:
    SecretValue = Annotated[str, Field(json_schema_extra={"x-neobot": {"secret": True}})]

    class SecretRoot(RootModel[SecretValue]):
        root: SecretValue = "synthetic-root-hidden"

    class Config(BaseModel):
        pair: tuple[SecretValue, str] = ("synthetic-tuple-hidden", "公开说明")

    root = export_model_schema(SecretRoot)
    assert root["writeOnly"] is True
    assert "default" not in root
    schema = export_model_schema(Config)
    assert "default" not in schema["properties"]["pair"]
    assert "synthetic" not in str(schema)
