"""真实配置接口对运行和停用插件的所有输入别名共用秘密保护。"""

import json
import tomllib

import httpx
import pytest
import tomlkit
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field

from neobot_app.builtin_plugins.dashboard.config_parts.secret_values import PluginSecretPolicy
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER
from neobot_modloader import Plugin

from test_dashboard_api import _login, _start_panel


def _model(kind):
    aliases = {
        "alias": {"alias": "external"},
        "validation_alias": {"validation_alias": "external"},
        "choices": {"validation_alias": AliasChoices("external", AliasPath("payload", 0, "entry"))},
        "path": {"validation_alias": AliasPath("payload", 0, "entry")},
    }

    class Credential(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        value: str = Field(
            default="synthetic-alias-model-private", **aliases[kind], json_schema_extra={"x-neobot": {"secret": True}}
        )
        label: str = "公开说明"

    class Config(BaseModel):
        nested: Credential | None = None
        rows: list[Credential] = []
        accounts: dict[str, Credential] = {}
        interval: int = 60

    return Config


def _credential(kind, naming, value):
    if naming == "canonical":
        return {"value": value, "label": "公开说明"}
    if kind in {"path", "choices"}:
        return {"payload": [{"entry": value, "label": "保留路径成员"}], "label": "公开说明"}
    return {"external": value, "label": "公开说明"}


@pytest.mark.parametrize("kind", ["alias", "validation_alias", "choices", "path"])
@pytest.mark.parametrize("naming", ["canonical", "alias"])
@pytest.mark.parametrize("running", [True, False])
async def test_http_alias_secrets_survive_placeholder_saves(tmp_path, monkeypatch, kind, naming, running):
    model = _model(kind)
    plugin = Plugin("demo", config=model)
    contract = plugin.surface.describe(plugin)
    defaults = {
        "nested": _credential(kind, naming, "synthetic-alias-default-private"),
        "rows": [_credential(kind, naming, "synthetic-alias-list-private")],
        "accounts": {"main": _credential(kind, naming, "synthetic-alias-dict-private")},
        "interval": 60,
    }
    assert model.model_validate(defaults).nested.value == "synthetic-alias-default-private"
    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "plugin_config_defaults", lambda name: defaults)
    monkeypatch.setattr(control, "config_model", lambda name: model if running else None)
    monkeypatch.setattr(control, "surface", lambda name: {"available": running, "contract": contract}, raising=False)
    path = control.plugin_config_path("demo")
    stored = {**defaults, "nested": _credential(kind, naming, "synthetic-alias-stored-private")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(stored), encoding="utf-8")
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient(trust_env=False) as client:
            read = await client.get(base + "/api/plugins/demo/config", headers=headers)
            assert read.status_code == 200, read.text
            assert "synthetic-alias-" not in read.text
            document = read.json()
            assert document["source_available"] is False
            assert document["source"] == ""
            submitted = document["config"]
            assert SECRET_PLACEHOLDER in json.dumps(submitted, ensure_ascii=False)
            submitted["interval"] = 30
            saved = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": submitted, "revision": document["revision"]},
            )
            assert saved.status_code == 200, saved.text
            assert "synthetic-alias-" not in saved.text
            actual = tomllib.loads(path.read_text(encoding="utf-8"))
            assert actual == {**stored, "interval": 30}
            assert model.model_validate(actual).nested.value == "synthetic-alias-stored-private"
    finally:
        await server.stop()


@pytest.mark.parametrize("running", [True, False])
def test_alias_policy_handles_negative_indexes_and_nested_recursive_models(running):
    class Credential(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        value: str = Field(
            validation_alias=AliasChoices("external", AliasPath("payload", -1, "entry")),
            json_schema_extra={"x-neobot": {"secret": True}},
        )
        child: "Credential | None" = None

    plugin = Plugin("aliases", config=Credential)
    schema = plugin.surface.describe(plugin)["config"]
    policy = PluginSecretPolicy(Credential) if running else PluginSecretPolicy(schema=schema)
    original = {
        "payload": [{"entry": "公开首项"}, {"entry": "synthetic-alias-private"}],
        "child": {"external": "synthetic-alias-child-private"},
    }
    masked = policy.mask(original)
    assert masked["payload"][0]["entry"] == "公开首项"
    assert masked["payload"][1]["entry"] == SECRET_PLACEHOLDER
    assert masked["child"]["external"] == SECRET_PLACEHOLDER
    assert policy.contains(original)
    assert policy.restore(masked, original) == original


@pytest.mark.parametrize("running", [True, False])
@pytest.mark.parametrize(
    "alias, original",
    [
        ("", {"": "synthetic-alias-private"}),
        (AliasPath("payload", True), {"payload": ["公开首项", "synthetic-alias-private"]}),
    ],
)
def test_policy_masks_empty_aliases_and_integer_subclass_indexes(running, alias, original):
    class Config(BaseModel):
        value: str = Field(validation_alias=alias, json_schema_extra={"x-neobot": {"secret": True}})

    assert Config.model_validate(original).value == "synthetic-alias-private"
    plugin = Plugin("aliases", config=Config)
    schema = plugin.surface.describe(plugin)["config"]
    policy = PluginSecretPolicy(Config) if running else PluginSecretPolicy(schema=schema)
    masked = policy.mask(original)
    assert "synthetic-alias-private" not in json.dumps(masked)
    assert policy.contains(original)
    assert policy.restore(masked, original) == original
