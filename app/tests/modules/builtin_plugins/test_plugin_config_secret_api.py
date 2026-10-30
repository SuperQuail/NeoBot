"""通过真实面板接口验证插件认证字段只写不读。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel, Field

from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER

from test_dashboard_api import _login, _start_panel


class _CookieAccount(BaseModel):
    cookie: str = "synthetic-model-service-cookie"
    username: str = "bot"


class _CookieConfig(BaseModel):
    cookie: str = "synthetic-model-cookie"
    interval: int = 60
    service: _CookieAccount = Field(default_factory=_CookieAccount)
    accounts: list[_CookieAccount] = Field(
        default_factory=lambda: [_CookieAccount(cookie="synthetic-model-list-cookie")]
    )


@pytest.mark.parametrize("can_manage", [True, False])
async def test_cookie_api_is_write_only_for_managers_and_readonly_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, can_manage: bool
) -> None:
    """模型 schema 替换编辑器描述后，管理与只读响应均不能回传 Cookie。"""
    server, control, base, _ = await _start_panel(tmp_path)
    original_defaults = control.plugin_config_defaults
    original_model = control.config_model
    monkeypatch.setattr(
        control,
        "plugin_config_defaults",
        lambda name: (
            {
                "cookie": "synthetic-manifest-cookie",
                "interval": 60,
                "service": {"cookie": "synthetic-manifest-service-cookie", "username": "bot"},
                "accounts": [{"cookie": "synthetic-manifest-list-cookie", "username": "bot"}],
            }
            if name == "demo"
            else original_defaults(name)
        ),
    )
    monkeypatch.setattr(control, "config_model", lambda name: _CookieConfig if name == "demo" else original_model(name))
    monkeypatch.setattr(type(server), "manage_plugins", property(lambda self: can_manage))
    path = control.plugin_config_path("demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        'cookie = "synthetic-stored-cookie"\ninterval = 60\n'
        '[service]\ncookie = "synthetic-stored-service-cookie"\nusername = "bot"\n'
        '[[accounts]]\ncookie = "synthetic-stored-list-cookie"\nusername = "bot"\n',
        encoding="utf-8",
    )
    secret_values = (
        "synthetic-stored-cookie",
        "synthetic-manifest-cookie",
        "synthetic-model-cookie",
        "synthetic-stored-service-cookie",
        "synthetic-manifest-service-cookie",
        "synthetic-model-service-cookie",
        "synthetic-stored-list-cookie",
        "synthetic-manifest-list-cookie",
        "synthetic-model-list-cookie",
    )

    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient() as client:
            read = await client.get(base + "/api/plugins/demo/config", headers=headers)
            assert read.status_code == 200, read.text
            document = read.json()
            assert document["config"]["cookie"] == SECRET_PLACEHOLDER
            assert document["source_available"] is False
            field = next(item for item in document["schema"] if item["name"] == "cookie")
            assert field["sensitive"] is True
            assert field["default"] == ""
            assert field["value"] == ""
            for secret in secret_values:
                assert secret not in read.text
            fields = {item["name"]: item for item in document["schema"]}
            masked_account = {"cookie": SECRET_PLACEHOLDER, "username": "bot"}
            assert fields["service"]["default"] == masked_account
            assert fields["accounts"]["default"] == [masked_account]

            saved = await client.post(
                base + "/api/plugins/demo/config",
                headers=headers,
                json={"config": {"cookie": "", "interval": 30}, "revision": document["revision"]},
            )
            assert saved.status_code == (200 if can_manage else 403), saved.text
            assert 'cookie = "synthetic-stored-cookie"' in path.read_text(encoding="utf-8")
            saved_document = json.dumps(saved.json())
            for secret in secret_values:
                assert secret not in saved_document
    finally:
        await server.stop()
