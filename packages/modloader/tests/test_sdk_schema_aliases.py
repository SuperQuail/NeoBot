"""配置契约保留输入别名语义，并清除别名默认值中的秘密。"""

import json
from collections.abc import Mapping, Sequence

import pytest
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, RootModel

from neobot_modloader import Plugin
from neobot_modloader.sdk.schema import export_model_schema


@pytest.mark.parametrize("kind", ["alias", "validation_alias", "choices", "path"])
def test_config_contract_records_alias_paths_without_changing_property_names(kind):
    aliases = {
        "alias": {"alias": "external"},
        "validation_alias": {"validation_alias": "external"},
        "choices": {"validation_alias": AliasChoices("external", AliasPath("payload", 0, "entry"))},
        "path": {"validation_alias": AliasPath("payload", 0, "entry")},
    }

    class Credential(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        value: str = Field(
            default="synthetic-alias-private", **aliases[kind], json_schema_extra={"x-neobot": {"secret": True}}
        )
        label: str = "公开说明"

    class Config(BaseModel):
        nested: Credential | None = None
        rows: list[Credential] = []
        accounts: dict[str, Credential] = {}

    plugin = Plugin("aliases", config=Config)
    schema = plugin.surface.describe(plugin)["config"]
    field = schema["$defs"]["Credential"]["properties"]["value"]
    assert set(schema["$defs"]["Credential"]["properties"]) == {"value", "label"}
    expected = [["payload", 0, "entry"]] if kind == "path" else [["external"]]
    if kind == "choices":
        expected.append(["payload", 0, "entry"])
    assert field["x-neobot"]["input_aliases"] == expected
    assert field["writeOnly"] is True
    assert "synthetic-alias-private" not in json.dumps(schema)
    assert "allOf" not in schema


def test_aliases_clean_nested_defaults_examples_and_recursive_definitions():
    class Credential(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        value: str = Field(
            default="synthetic-field-private",
            validation_alias=AliasChoices("external", AliasPath("payload", -1, "entry")),
            json_schema_extra={"x-neobot": {"secret": True}},
        )
        label: str = "公开说明"
        child: "Credential | None" = None

    class Config(BaseModel):
        nested: Credential | None = Field(
            default={"external": "synthetic-default-private", "label": "公开默认"},
            examples=[{"payload": [{"entry": "synthetic-example-private", "label": "公开示例"}]}],
        )
        rows: list[Credential] = [{"external": "synthetic-list-private", "label": "公开列表"}]
        accounts: dict[str, Credential] = {
            "main": {"payload": [{"entry": "synthetic-dict-private"}], "label": "公开字典"}
        }

    schema = export_model_schema(Config, by_alias=False)
    assert "synthetic-" not in json.dumps(schema)
    assert schema["properties"]["nested"]["default"] == {"label": "公开默认"}
    assert schema["properties"]["nested"]["examples"] == [{"payload": [{"label": "公开示例"}]}]
    assert schema["properties"]["rows"]["default"] == [{"label": "公开列表"}]
    assert schema["properties"]["accounts"]["default"]["main"]["label"] == "公开字典"
    assert schema["$defs"]["Credential"]["properties"]["value"]["x-neobot"]["input_aliases"] == [
        ["external"],
        ["payload", -1, "entry"],
    ]


def test_config_alias_metadata_never_runs_a_default_factory_or_mutates_model_schema():
    calls = []

    class Config(BaseModel):
        value: str = Field(default_factory=lambda: calls.append(True), alias="external")

    before = Config.model_json_schema(by_alias=False)
    schema = export_model_schema(Config, by_alias=False)
    assert calls == []
    assert Config.model_json_schema(by_alias=False) == before
    assert schema["properties"]["value"]["x-neobot"]["input_aliases"] == [["external"]]
    assert set(export_model_schema(Config)["properties"]) == {"external"}
    assert set(export_model_schema(Config, mode="serialization")["properties"]) == {"external"}


def test_alias_paths_cover_generic_collections_root_models_and_tuple_items():
    class Credential(BaseModel):
        value: str = Field(alias="external", json_schema_extra={"x-neobot": {"secret": True}})

    class Config(RootModel[tuple[Sequence[Credential], Mapping[str, Credential]]]):
        pass

    schema = export_model_schema(Config, by_alias=False)
    field = schema["$defs"]["Credential"]["properties"]["value"]
    assert field["x-neobot"]["input_aliases"] == [["external"]]


@pytest.mark.parametrize("alias, expected", [("", [[""]]), (AliasPath("payload", True), [["payload", 1]])])
def test_empty_aliases_and_integer_subclasses_keep_their_validated_paths(alias, expected):
    class Config(BaseModel):
        value: str = Field(validation_alias=alias, json_schema_extra={"x-neobot": {"secret": True}})

    schema = export_model_schema(Config, by_alias=False)
    assert schema["properties"]["value"]["x-neobot"]["input_aliases"] == expected
