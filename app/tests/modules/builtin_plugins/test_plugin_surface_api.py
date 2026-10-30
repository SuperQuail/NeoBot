"""通过真实面板 HTTP 路由验证统一 SDK 权限与输入边界。"""

import httpx
import pytest
from pydantic import BaseModel

from neobot_modloader import Plugin

from test_dashboard_api import _login, _start_panel


@pytest.mark.parametrize("can_manage", [True, False])
async def test_surface_read_and_action_permission_cannot_be_spoofed(tmp_path, monkeypatch, can_manage):
    server, control, base, _ = await _start_panel(tmp_path)
    plugin = Plugin("demo")
    calls = []

    class Input(BaseModel):
        value: int

    @plugin.action("save", input_model=Input)
    async def save(values, invocation):
        calls.append(values.value)
        return {"value": values.value, "identity": invocation.identity}

    @plugin.action("status", permission="read")
    async def status(values, invocation):
        return {"completed": True}

    monkeypatch.setattr(type(server), "manage_plugins", property(lambda self: can_manage))
    monkeypatch.setattr(
        control,
        "surface",
        lambda name: {
            "contract": plugin.surface.describe(plugin),
            "available": True,
            "state": "running",
            "source": "runtime",
        },
        raising=False,
    )

    async def invoke(name, action, values, invocation):
        return await plugin.surface.invoke(plugin, action, values, invocation)

    monkeypatch.setattr(control, "invoke_action", invoke, raising=False)
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient() as client:
            description = await client.get(base + "/api/plugins/demo/surface", headers=headers)
            assert description.status_code == 200
            assert ("manage" in description.json()["permissions"]) is can_manage
            result = await client.post(
                base + "/api/plugins/demo/actions/save",
                headers=headers,
                json={"values": {"value": 5}, "permissions": ["manage"], "identity": "forged"},
            )
            assert result.status_code == (200 if can_manage else 403), result.text
            assert calls == ([5] if can_manage else [])
            if can_manage:
                assert result.json()["result"] == {"value": 5, "identity": "dashboard"}
            readable = await client.post(
                base + "/api/plugins/demo/actions/status", headers=headers, json={"values": {}}
            )
            assert readable.status_code == 200
            assert readable.json()["result"] == {"completed": True}
            no_csrf = await client.post(base + "/api/plugins/demo/actions/status", headers={"X-Token": token}, json={})
            assert no_csrf.status_code == 403
    finally:
        await server.stop()
