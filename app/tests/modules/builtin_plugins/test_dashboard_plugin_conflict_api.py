"""spec(4) Part D：面板安装接口的冲突态契约（R27 / D24 / A67-A69 的接口面）。

磁盘语义（零变化 / 备份路径 / 官方保留字）由 packages/modloader/tests/
test_plugin_conflict.py 用真实安装器覆盖；这里验证 HTTP 接口如何透传
dry_run / replace，以及冲突如何变成结构化响应。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_modloader import PluginOperationResult

from test_dashboard_api import (
    PASSWORD,
    _FakeAdapter,
    _NullLogger,
    _free_port,
    _login,
)


class _InstallControl:
    """只实现安装相关通道的控制面替身。"""

    def __init__(self) -> None:
        self.installer_available = True
        self.install_calls: list[dict] = []
        self.probe_calls: list[str] = []
        self.next_result = PluginOperationResult(ok=True, name="demo", version="1.0.0")
        self.probe_result: dict = {"conflict": False, "existing": None, "official": False}

    def probe(self, name: str) -> dict:
        self.probe_calls.append(name)
        return dict(self.probe_result)

    async def install(self, repo: str, *, branch=None, replace=False, start=True, dry_run=False):
        self.install_calls.append(
            {"repo": repo, "branch": branch, "replace": replace, "dry_run": dry_run}
        )
        return self.next_result

    def snapshot(self):
        return []

    def plugin_config_path(self, name: str) -> Path:
        return Path("/tmp") / name / "config.toml"


async def _start_panel(tmp_path: Path, control: _InstallControl):
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=control,
        services=None,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}"


@pytest.fixture()
async def install_panel(tmp_path: Path):
    control = _InstallControl()
    server, base = await _start_panel(tmp_path, control)
    try:
        yield {"base": base, "control": control}
    finally:
        await server.stop()


async def _headers(base: str) -> dict[str, str]:
    token, csrf = await _login(base)
    return {"X-Token": token, "X-CSRF-Token": csrf}


async def test_dry_run_is_passed_through_and_conflict_returned(install_panel) -> None:
    """A67：dry_run=true 只探测；冲突以 conflict 字段回传（HTTP 200）。"""
    base = install_panel["base"]
    control: _InstallControl = install_panel["control"]
    conflict = {
        "kind": "existing_plugin",
        "requested": {"name": "demo", "version": "2.0.0", "repo": "owner/demo", "branch": "main"},
        "existing": {"name": "demo", "version": "1.0.0", "repo": "other/demo", "path": "/x/demo", "official": False},
        "message": "已存在同名插件 demo；只能二选一",
        "reserved": False,
    }
    control.next_result = PluginOperationResult(
        ok=True, name="demo", version="2.0.0", conflict=conflict, dry_run=True
    )
    headers = await _headers(base)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/plugins/install",
            json={"repo": "owner/demo", "dry_run": True},
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["version"] == "2.0.0"
    assert payload["conflict"]["existing"]["version"] == "1.0.0"
    assert control.install_calls == [
        {"repo": "owner/demo", "branch": None, "replace": False, "dry_run": True}
    ]


async def test_install_conflict_returns_409_with_structure(install_panel) -> None:
    """A67/A68：未确认替换 -> 409 + 结构化冲突（含两侧来源与版本）。"""
    base = install_panel["base"]
    control: _InstallControl = install_panel["control"]
    conflict = {
        "kind": "existing_plugin",
        "requested": {"name": "demo", "version": "2.0.0", "repo": "owner/demo", "branch": "main"},
        "existing": {"name": "demo", "version": "1.0.0", "repo": "other/demo", "path": "/x/demo", "official": False},
        "message": "已存在同名插件 demo；只能二选一",
        "reserved": False,
    }
    control.next_result = PluginOperationResult(
        ok=False, name="demo", version="2.0.0", error=conflict["message"], conflict=conflict
    )
    headers = await _headers(base)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/plugins/install",
            json={"repo": "owner/demo", "replace": False},
            headers=headers,
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert payload["conflict"]["existing"]["repo"] == "other/demo"
    assert payload["conflict"]["requested"]["repo"] == "owner/demo"
    assert "只能二选一" in payload["error"]
    assert control.install_calls[0]["replace"] is False


async def test_explicit_replace_echoes_backup_path(install_panel) -> None:
    """A68：显式 replace=true -> 200，并回显 backup_path。"""
    base = install_panel["base"]
    control: _InstallControl = install_panel["control"]
    control.next_result = PluginOperationResult(
        ok=True,
        name="demo",
        version="2.0.0",
        path=Path("/plugins/demo"),
        backup_path=Path("/backups/demo-20260913"),
    )
    headers = await _headers(base)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/plugins/install",
            json={"repo": "owner/demo", "replace": True},
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    backup = str(Path("/backups/demo-20260913"))
    assert payload["ok"] is True
    assert Path(payload["backup_path"]) == Path(backup)
    assert backup in payload["message"]
    assert control.install_calls[0]["replace"] is True
    assert control.install_calls[0]["dry_run"] is False


async def test_official_reserved_id_is_rejected(install_panel) -> None:
    """A69：官方 ID 保留字 -> 拒绝，文案指向「官方插件随本体更新」。"""
    base = install_panel["base"]
    control: _InstallControl = install_panel["control"]
    conflict = {
        "kind": "official",
        "requested": {"name": "dashboard", "version": "9.9.9", "repo": "evil/dashboard", "branch": "main"},
        "existing": {"name": "dashboard", "version": "1.0.0", "repo": "", "path": "/official/dashboard", "official": True},
        "message": "插件 ID dashboard 是官方插件保留字：官方插件随本体更新，不能在面板内更新",
        "reserved": True,
    }
    control.next_result = PluginOperationResult(
        ok=False, name="dashboard", version="9.9.9", error=conflict["message"], conflict=conflict
    )
    headers = await _headers(base)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/plugins/install",
            json={"repo": "evil/dashboard"},
            headers=headers,
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["conflict"]["reserved"] is True
    assert "官方插件随本体更新" in payload["error"]


async def test_probe_endpoint_reports_conflict(install_panel) -> None:
    """A67：GET /api/plugins/probe 只读探测。"""
    base = install_panel["base"]
    control: _InstallControl = install_panel["control"]
    control.probe_result = {
        "conflict": True,
        "existing": {"name": "demo", "version": "1.0.0", "repo": "other/demo", "official": False},
        "official": False,
        "message": "已存在同名插件 demo",
    }
    headers = await _headers(base)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            base + "/api/plugins/probe", params={"name": "demo"}, headers=headers
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conflict"] is True
    assert payload["existing"]["version"] == "1.0.0"
    assert control.probe_calls == ["demo"]


async def test_install_requires_login(install_panel) -> None:
    base = install_panel["base"]
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/plugins/install", json={"repo": "owner/demo"})

    assert response.status_code == 401


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__]))
