"""凭据类型保存真实值，校验错误不能回显已恢复的存量凭据。"""

import tomllib

import httpx
import pytest
from pydantic import BaseModel, Field, SecretBytes, SecretStr, field_validator, model_validator

from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER

from test_dashboard_api import _login, _start_panel


@pytest.mark.parametrize("secret_type", [SecretStr, SecretBytes])
async def test_secret_value_is_not_replaced_by_pydantic_display_mask(tmp_path, monkeypatch, secret_type):
    class Config(BaseModel):
        value: secret_type
        interval: int = 60

    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "config_model", lambda name: Config)
    monkeypatch.setattr(
        control, "plugin_config_defaults", lambda name: {"value": "synthetic-private-type", "interval": 60}
    )
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient(trust_env=False) as client:
            for value, expected in (
                (SECRET_PLACEHOLDER, "synthetic-private-type"),
                ("synthetic-private-replaced", "synthetic-private-replaced"),
            ):
                document = (await client.get(base + "/api/plugins/demo/config", headers=headers)).json()
                response = await client.post(
                    base + "/api/plugins/demo/config",
                    headers=headers,
                    json={"config": {"value": value, "interval": 30}, "revision": document["revision"]},
                )
                assert response.status_code == 200, response.text
                assert "synthetic-private-" not in response.text
                stored = tomllib.loads(control.plugin_config_path("demo").read_text(encoding="utf-8"))
                assert stored["value"] == expected
                assert stored["value"] != "**********"
    finally:
        await server.stop()


class FieldRejects(BaseModel):
    value: str = Field(json_schema_extra={"sensitive": True})

    @field_validator("value")
    @classmethod
    def rejects(cls, value):
        raise ValueError(f"拒绝凭据 {value}")


class ModelRejects(BaseModel):
    value: str = Field(json_schema_extra={"sensitive": True})

    @model_validator(mode="after")
    def rejects(self):
        raise ValueError(f"拒绝凭据 {self.value}")


async def test_hidden_container_does_not_expose_private_dictionary_keys_in_error_paths(tmp_path, monkeypatch):
    class Config(BaseModel):
        vault: dict[str, int] = Field(json_schema_extra={"writeOnly": True})

    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "config_model", lambda name: Config)
    monkeypatch.setattr(
        control,
        "plugin_config_defaults",
        lambda name: {
            "vault": {"synthetic-private-dictionary-key": "invalid integer"},
        },
    )
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                base + "/api/plugins/demo/config",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={"config": {"vault": SECRET_PLACEHOLDER}, "revision": ""},
            )
            assert response.status_code == 400, response.text
            assert "synthetic-private-dictionary-key" not in response.text
            assert response.json()["errors"][0]["path"] == "vault"
    finally:
        await server.stop()


@pytest.mark.parametrize("model", [FieldRejects, ModelRejects])
async def test_plugin_validation_errors_never_return_restored_secret_values(tmp_path, monkeypatch, model):
    server, control, base, _ = await _start_panel(tmp_path)
    monkeypatch.setattr(control, "config_model", lambda name: model)
    monkeypatch.setattr(control, "plugin_config_defaults", lambda name: {"value": "synthetic-private-rejected"})
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                base + "/api/plugins/demo/config",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={"config": {"value": SECRET_PLACEHOLDER}, "revision": ""},
            )
            assert response.status_code == 400, response.text
            assert "synthetic-private-rejected" not in response.text
            assert response.json()["errors"][0]["path"] == ("value" if model is FieldRejects else "config")
            assert control.plugin_config_path("demo").exists() is False
    finally:
        await server.stop()
