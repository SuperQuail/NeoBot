"""面板必须透传运行时服务诊断，旧运行时仍可读取插件列表。"""

from __future__ import annotations

import httpx

from tests.modules.builtin_plugins.test_dashboard_api import _login, panel as panel


async def test_plugin_list_exposes_service_dependencies(panel):
    _server, control, base, _config_path = panel
    consumer = control.snapshots[1]
    consumer.services = (
        {
            "service": "http",
            "kind": "required",
            "status": "missing",
            "specifier": ">=1.0",
            "provider": "",
            "version": "",
            "message": "必需服务：http（未加载）",
        },
    )
    consumer.service_conflicts = (
        {"service": "server", "winner": "primary", "loser": "demo", "message": "服务由 primary 提供"},
    )
    consumer.service_undeclared = ("legacy",)
    consumer.dependency_status = "blocked"
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/plugins", headers={"X-Token": token})
    assert response.status_code == 200
    items = {item["name"]: item for item in response.json()["items"]}
    assert items["demo"]["services"] == list(consumer.services)
    assert items["demo"]["service_conflicts"] == list(consumer.service_conflicts)
    assert items["demo"]["service_undeclared"] == ["legacy"]
    assert items["demo"]["dependency_status"] == "blocked"
    assert items["dashboard"]["services"] == []
    assert items["dashboard"]["service_conflicts"] == []
    assert items["dashboard"]["dependency_status"] == "ok"


async def test_service_diagnostics_require_panel_auth(panel):
    _server, _control, base, _config_path = panel
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/plugins")
    assert response.status_code == 401
