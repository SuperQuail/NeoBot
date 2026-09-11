"""面板待机接口：/api/admin/power 与 standby / resume / reboot / standby-onebot。"""

from __future__ import annotations

import asyncio

from pathlib import Path

import httpx

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_app.runtime.standby_service import StandbyService

from test_dashboard_api import PASSWORD, _FakeAdapter, _FakeControl, _free_port, _login


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _Services:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, name: str, default=None):
        return self._mapping.get(name, default)


async def _wait_standby(service, expected: bool, seconds: float = 5.0) -> bool:
    """进入待机/软重启在服务端后台执行：等状态落定再断言。"""
    for _ in range(int(seconds * 20)):
        if service.is_standby() is expected:
            return True
        await asyncio.sleep(0.05)
    return False


async def _panel(tmp_path: Path, *, with_service: bool):
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-test-panel\n", encoding="utf-8")
    standby = StandbyService()
    services = _Services({"standby_service": standby} if with_service else {})
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=_FakeControl(),
        services=services,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}", standby


async def test_power_endpoints_require_login(tmp_path: Path) -> None:
    server, base, _ = await _panel(tmp_path, with_service=True)
    try:
        async with httpx.AsyncClient() as client:
            assert (await client.get(base + "/api/admin/power")).status_code == 401
            assert (await client.post(base + "/api/admin/standby", json={})).status_code == 401
            assert (await client.post(base + "/api/admin/resume", json={})).status_code == 401
            assert (await client.post(base + "/api/admin/reboot", json={})).status_code == 401
            assert (
                await client.post(base + "/api/admin/standby/onebot", json={"enabled": False})
            ).status_code == 401
    finally:
        await server.stop()


async def test_power_status_and_standby_round_trip(tmp_path: Path) -> None:
    server, base, standby = await _panel(tmp_path, with_service=True)
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/admin/power", headers={"X-Token": token})
            payload = status.json()
            assert status.status_code == 200
            assert payload["available"] is True
            assert payload["standby"] is False
            assert payload["connect_onebot"] is True

            entered = await client.post(
                base + "/api/admin/standby", headers=headers, json={"reason": "token 风暴"}
            )
            assert entered.status_code == 200, entered.text
            assert "已开始进入待机" in entered.json()["message"]
            assert await _wait_standby(standby, True), "接口后台执行，状态应很快落定"
            assert standby.status()["reason"] == "token 风暴"

            overview = await client.get(base + "/api/overview", headers={"X-Token": token})
            assert overview.json()["standby"] is True

            resumed = await client.post(base + "/api/admin/resume", headers=headers, json={})
            assert resumed.status_code == 200, resumed.text
            assert "已开始软重启运行" in resumed.json()["message"]
            assert await _wait_standby(standby, False), "软重启后应回到运行中"
    finally:
        await server.stop()


async def test_standby_onebot_toggle(tmp_path: Path) -> None:
    server, base, standby = await _panel(tmp_path, with_service=True)
    try:
        token, csrf = await _login(base)
        headers = {"X-Token": token, "X-CSRF-Token": csrf}
        async with httpx.AsyncClient() as client:
            off = await client.post(
                base + "/api/admin/standby/onebot", headers=headers, json={"enabled": False}
            )
            assert off.status_code == 200, off.text
            assert off.json()["connect_onebot"] is False
        assert standby.connect_onebot is False
    finally:
        await server.stop()


async def test_power_without_service_reports_unavailable(tmp_path: Path) -> None:
    server, base, _ = await _panel(tmp_path, with_service=False)
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/admin/power", headers={"X-Token": token})
            assert status.status_code == 200
            assert status.json()["available"] is False
            denied = await client.post(
                base + "/api/admin/standby",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={},
            )
            assert denied.status_code == 503
    finally:
        await server.stop()
