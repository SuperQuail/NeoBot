"""官方 dashboard 插件：运维冻结接口（状态 / 冻结 / 解冻）集成测试。

直接启动真实 aiohttp 服务并请求，覆盖鉴权、冻结状态透出与解冻回滚。
"""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_app.runtime.freeze_service import FreezeService

PASSWORD = "NeoBot-Panel-2026"


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _FakeAdapter:
    connected = True

    async def call_api(self, action: str, params: dict, timeout: float = 5.0):
        if action == "get_login_info":
            return {"status": "ok", "data": {"user_id": 10001, "nickname": "测试机器人"}}
        return {"status": "ok", "data": {}}


class _Services:
    """最小宿主服务注册表：dashboard 只用 get() 与 describe()。"""

    def __init__(self, mapping: dict) -> None:
        self._mapping = dict(mapping)

    def get(self, name: str, default=None):
        value = self._mapping.get(name)
        return default if value is None else value

    def describe(self):
        return [
            {"name": name, "description": "", "available": True}
            for name in self._mapping
        ]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_panel(tmp_path: Path, *, services=None):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = "0.6.0"\n', encoding="utf-8"
    )
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)

    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=None,
        services=services,
        config_path=config_path,
        env_path=tmp_path / ".env",
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}"


async def _login(base: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["token"], payload["csrf_token"]


@pytest.fixture()
async def frozen_panel(tmp_path: Path):
    freeze_service = FreezeService()
    server, base = await _start_panel(
        tmp_path, services=_Services({"freeze_service": freeze_service})
    )
    try:
        yield freeze_service, base
    finally:
        await server.stop()


@pytest.fixture()
async def bare_panel(tmp_path: Path):
    server, base = await _start_panel(tmp_path, services=_Services({}))
    try:
        yield base
    finally:
        await server.stop()


async def test_freeze_endpoints_require_login(frozen_panel) -> None:
    _, base = frozen_panel
    async with httpx.AsyncClient() as client:
        status = await client.get(base + "/api/admin/freeze")
        freeze = await client.post(base + "/api/admin/freeze", json={})
        unfreeze = await client.post(base + "/api/admin/unfreeze")

    assert status.status_code == 401
    assert freeze.status_code == 401
    assert unfreeze.status_code == 401


async def test_freeze_status_reports_current_state(frozen_panel) -> None:
    freeze_service, base = frozen_panel
    token, _ = await _login(base)
    headers = {"X-Token": token}

    async with httpx.AsyncClient() as client:
        idle = await client.get(base + "/api/admin/freeze", headers=headers)

    assert idle.status_code == 200
    body = idle.json()
    assert body["available"] is True
    assert body["frozen"] is False

    freeze_service.freeze(reason="token 风暴", operator="panel:test")
    async with httpx.AsyncClient() as client:
        frozen = await client.get(base + "/api/admin/freeze", headers=headers)

    body = frozen.json()
    assert body["frozen"] is True
    assert body["reason"] == "token 风暴"
    assert body["remaining_seconds"] is None


async def test_freeze_and_unfreeze_round_trip(frozen_panel) -> None:
    freeze_service, base = frozen_panel
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        frozen = await client.post(
            base + "/api/admin/freeze",
            headers=headers,
            json={"reason": "面板手动熔断", "seconds": 600},
        )

    assert frozen.status_code == 200, frozen.text
    body = frozen.json()
    assert body["frozen"] is True
    assert body["reason"] == "面板手动熔断"
    assert 500 <= body["remaining_seconds"] <= 600
    assert freeze_service.is_frozen() is True

    async with httpx.AsyncClient() as client:
        released = await client.post(base + "/api/admin/unfreeze", headers=headers)

    assert released.status_code == 200, released.text
    assert released.json()["frozen"] is False
    assert freeze_service.is_frozen() is False


async def test_freeze_rejects_invalid_seconds(frozen_panel) -> None:
    freeze_service, base = frozen_panel
    token, csrf = await _login(base)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/admin/freeze",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"seconds": "abc"},
        )

    assert response.status_code == 400
    assert "seconds" in response.json()["error"]
    assert freeze_service.is_frozen() is False


async def test_freeze_without_service_reports_unavailable(bare_panel) -> None:
    base = bare_panel
    token, csrf = await _login(base)
    headers = {"X-Token": token}

    async with httpx.AsyncClient() as client:
        status = await client.get(base + "/api/admin/freeze", headers=headers)
        frozen = await client.post(
            base + "/api/admin/freeze",
            headers={**headers, "X-CSRF-Token": csrf},
            json={},
        )

    assert status.json()["available"] is False
    assert status.json()["frozen"] is False
    assert frozen.status_code == 503


async def test_overview_exposes_frozen_flag(frozen_panel) -> None:
    freeze_service, base = frozen_panel
    token, _ = await _login(base)
    freeze_service.freeze(reason="storm")

    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/overview", headers={"X-Token": token})

    assert response.status_code == 200
    assert response.json()["frozen"] is True
