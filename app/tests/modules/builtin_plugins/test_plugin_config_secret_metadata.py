"""显式敏感语义贯穿原配置接口与页面桥接复用的读改存流程。"""

import json
import tomllib
from typing import Annotated

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field

from neobot_app.builtin_plugins.dashboard.config_parts.describe import describe_pydantic_model
from neobot_app.builtin_plugins.dashboard.plugin_config import PluginConfigEditor, PluginConfigError
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER
from neobot_modloader.sdk.schema import export_model_schema
from neobot_modloader import Plugin

from test_dashboard_api import _login, _start_panel


class Credential(BaseModel):
    value: str = Field(default="synthetic-private-nested", json_schema_extra={"sensitive": True})
    name: str = "公开名称"


class PrivateConfig(BaseModel):
    value: str = Field(
        default="synthetic-private-top", pattern="^synthetic-", json_schema_extra={"x-neobot": {"secret": True}}
    )
    other: str = Field(default="synthetic-private-other", json_schema_extra={"writeOnly": True})
    nested: Credential | None = Field(default_factory=Credential)
    rows: list[Credential] = Field(default_factory=lambda: [Credential(value="synthetic-private-list")])
    values: dict[str, Annotated[str, Field(json_schema_extra={"writeOnly": True})]] = Field(
        default_factory=lambda: {"first": "synthetic-private-dictionary"}
    )
    interval: int = 60


@pytest.mark.parametrize("alias", ["alias", "validation_alias"])
async def test_alias_secret_fields_remain_private_when_the_plugin_is_disabled(tmp_path, monkeypatch, alias):
    class Aliased(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        value: str = Field(
            default="synthetic-private-alias", **{alias: "external"}, json_schema_extra={"x-neobot": {"secret": True}}
        )

    class Config(BaseModel):
        nested: Aliased = Field(default_factory=Aliased)
        rows: list[Aliased] = Field(default_factory=lambda: [Aliased()])
        interval: int = 60

    plugin = Plugin("demo", config=Config)
    contract = plugin.surface.describe(plugin)
    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "plugin_config_defaults", lambda name: Config().model_dump())
    monkeypatch.setattr(control, "config_model", lambda name: None)
    monkeypatch.setattr(control, "surface", lambda name: {"available": False, "contract": contract}, raising=False)
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(base + "/api/plugins/demo/config", headers=headers)
            assert response.status_code == 200, response.text
            assert "synthetic-private-alias" not in response.text
            document = response.json()
            assert document["source_available"] is False
            document["config"]["interval"] = 30
            saved = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": document["config"], "revision": document["revision"]},
            )
            assert saved.status_code == 200, saved.text
            assert "synthetic-private-alias" not in saved.text
            stored = tomllib.loads(control.plugin_config_path("demo").read_text(encoding="utf-8"))
            assert stored["nested"]["value"] == stored["rows"][0]["value"] == "synthetic-private-alias"
    finally:
        await server.stop()


async def test_disabled_plugin_uses_static_secret_schema_without_importing_code(tmp_path, monkeypatch):
    server, control, base, _ = await _start_panel(tmp_path)
    defaults = PrivateConfig().model_dump()
    monkeypatch.setattr(control, "plugin_config_defaults", lambda name: defaults)
    monkeypatch.setattr(control, "config_model", lambda name: None)
    monkeypatch.setattr(
        control,
        "surface",
        lambda name: {
            "available": False,
            "contract": {"config": export_model_schema(PrivateConfig)},
        },
        raising=False,
    )
    try:
        token, _ = await _login(base)
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(base + "/api/plugins/demo/config", headers={"X-Token": token})
            assert response.status_code == 200, response.text
            assert "synthetic-private-" not in response.text
            assert response.json()["source_available"] is False
    finally:
        await server.stop()


def test_editor_honors_explicit_secret_metadata_in_all_public_outputs(tmp_path):
    defaults = PrivateConfig().model_dump()
    editor = PluginConfigEditor(tmp_path / "config.toml", defaults=defaults, model=PrivateConfig)
    document = editor.read()
    document["schema"] = describe_pydantic_model(PrivateConfig, document["config"])
    serialized = json.dumps(document, ensure_ascii=False)
    for value in (
        defaults["value"],
        defaults["other"],
        defaults["nested"]["value"],
        defaults["rows"][0]["value"],
        defaults["values"]["first"],
    ):
        assert value not in serialized
    assert document["source_available"] is False
    assert document["source"] == ""
    assert document["config"]["value"] == SECRET_PLACEHOLDER
    assert document["config"]["nested"] == {"value": SECRET_PLACEHOLDER, "name": "公开名称"}
    assert document["config"]["values"]["first"] == SECRET_PLACEHOLDER
    fields = {item["name"]: item for item in document["schema"]}
    assert fields["value"]["sensitive"] is True
    assert fields["value"]["has_value"] is True
    assert fields["value"]["value"] == fields["value"]["default"] == ""
    assert fields["nested"]["default"]["value"] == SECRET_PLACEHOLDER
    with pytest.raises(PluginConfigError, match="禁用源码编辑"):
        editor.save(source="interval = 30\n")


@pytest.mark.parametrize("exists", [False, True])
async def test_real_config_api_restores_secrets_before_validation_and_never_reads_them_back(
    tmp_path, monkeypatch, exists
):
    server, control, base, _ = await _start_panel(tmp_path)
    defaults = PrivateConfig().model_dump()
    monkeypatch.setattr(control, "plugin_config_defaults", lambda name: defaults)
    monkeypatch.setattr(control, "config_model", lambda name: PrivateConfig)
    path = control.plugin_config_path("demo")
    if exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('value = "synthetic-private-stored"\ninterval = 60\n', encoding="utf-8")
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(base + "/api/plugins/demo/config", headers=headers)
            response.raise_for_status()
            document = response.json()
            assert document["source_available"] is False
            assert "synthetic-private-" not in response.text
            submitted = document["config"]
            submitted["value"] = ""
            submitted["interval"] = 30
            saved = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": submitted, "revision": document["revision"]},
            )
            assert saved.status_code == 200, saved.text
            assert "synthetic-private-" not in saved.text
            stored = tomllib.loads(path.read_text(encoding="utf-8"))
            assert stored["value"] == ("synthetic-private-stored" if exists else defaults["value"])
            assert stored["rows"][0]["value"] == defaults["rows"][0]["value"]
            assert stored["values"]["first"] == defaults["values"]["first"]
            assert stored["interval"] == 30
            submitted["value"] = "synthetic-private-replaced"
            updated = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": submitted, "revision": saved.json()["revision"]},
            )
            assert updated.status_code == 200, updated.text
            assert "synthetic-private-" not in updated.text
            assert tomllib.loads(path.read_text(encoding="utf-8"))["value"] == "synthetic-private-replaced"
    finally:
        await server.stop()
