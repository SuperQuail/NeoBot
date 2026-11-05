"""扩展接口使用宿主统一的初始化、会话与管理权限边界。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from aiohttp import web

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.builtin_plugins.starship.config import StarshipConfig
from neobot_app.builtin_plugins.starship.web_extension import StarshipWebExtension
from neobot_app.panel_auth import PanelPasswordStore

from test_dashboard_api import PASSWORD, _FakeAdapter, _NullLogger, _free_port, _login


class _GameApi:
    """只记录分发结果，鉴权测试不会操作游戏数据库。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def response(self, action: str) -> web.Response:
        self.calls.append(action)
        return web.json_response({"ok": True, "action": action})

    async def scores(self, request):
        return self.response("scores")

    async def submit_score(self, request):
        return self.response("submit_score")

    async def unlock(self, request):
        return self.response("unlock")

    async def reset_scores(self, request):
        return self.response("reset_scores")


class _LegacyExtension:
    """未提供逐请求权限的旧扩展仍应有安全的默认规则。"""

    prefixes = ("/legacy",)
    auth_prefixes = ("/legacy/api",)

    def __init__(self) -> None:
        self.calls = 0

    async def handle_request(self, request, path):
        self.calls += 1
        return web.json_response({"ok": True})


@pytest.fixture
async def extension_panel(tmp_path: Path):
    servers: list[DashboardServer] = []

    async def create(*, configured=True, base_path="", **config_options):
        root = tmp_path / f"panel-{len(servers)}"
        root.mkdir()
        config_path = root / "config.toml"
        config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
        env_path = root / ".env"
        env_path.write_text("", encoding="utf-8")
        data_dir = root / "data"
        if configured:
            PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
        server = DashboardServer(
            plugin_name="dashboard",
            config=DashboardConfig(
                host="127.0.0.1",
                port=_free_port(),
                base_path=base_path,
                trust_proxy_headers=True,
                **config_options,
            ),
            data_dir=data_dir,
            logger=_NullLogger(),
            adapter=_FakeAdapter(),
            config_path=config_path,
            env_path=env_path,
            backup_dir=root / "backup",
        )
        web_root = root / "web"
        (web_root / "assets").mkdir(parents=True)
        (web_root / "index.html").write_text("<p>game</p>", encoding="utf-8")
        (web_root / "assets" / "game.css").write_text("body {}", encoding="utf-8")
        api = _GameApi()
        extension = StarshipWebExtension(config=StarshipConfig(), api=api, logger=_NullLogger(), web_root=web_root)
        server.register_extension("starship", extension)
        await server.start()
        servers.append(server)
        return server, api, f"http://127.0.0.1:{server.bound_port}{base_path}"

    try:
        yield create
    finally:
        for server in reversed(servers):
            await server.stop()


@pytest.mark.parametrize("base_path", ["", "/nb"])
@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("method, endpoint", [("GET", "health"), ("POST", "scores/reset")])
async def test_extension_api_requires_password_setup(extension_panel, base_path, remote, method, endpoint):
    _, api, base = await extension_panel(configured=False, base_path=base_path)
    headers = {"X-Forwarded-For": "203.0.113.9"} if remote else {}
    async with httpx.AsyncClient() as client:
        response = await client.request(method, base + "/game/api/" + endpoint, headers=headers)
    assert response.status_code == 403
    assert response.json()["setup_required"] is True
    assert response.json()["loopback"] is not remote
    assert api.calls == []


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("base_path", ["", "/nb"])
async def test_extension_static_resources_remain_public(extension_panel, configured, base_path):
    _, _, base = await extension_panel(configured=configured, base_path=base_path)
    async with httpx.AsyncClient() as client:
        page = await client.get(base + "/game/")
        asset = await client.get(base + "/game/assets/game.css")
    assert page.status_code == 200
    assert page.text == "<p>game</p>"
    assert asset.status_code == 200
    assert asset.text == "body {}"


@pytest.mark.parametrize("base_path", ["", "/nb"])
async def test_extension_api_requires_session(extension_panel, base_path):
    _, api, base = await extension_panel(base_path=base_path)
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/game/api/scores")
        write = await client.post(base + "/game/api/scores/reset", json={})
    assert read.status_code == 401
    assert write.status_code == 401
    assert api.calls == []


@pytest.mark.parametrize("endpoint", ["scores", "achievements", "scores/reset"])
async def test_extension_writes_require_csrf(extension_panel, endpoint):
    _, api, base = await extension_panel()
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/game/api/" + endpoint, headers={"X-Token": token}, json={})
    assert response.status_code == 403
    assert "CSRF" in response.json()["error"]
    assert api.calls == []


@pytest.mark.parametrize("config_options", [{"manage_plugins": False}, {"allow_remote_manage": False}])
@pytest.mark.parametrize("endpoint", ["scores/reset", "scores/reset/", "scores/reset/extra"])
async def test_extension_management_write_requires_manage_permission(extension_panel, config_options, endpoint):
    _, api, base = await extension_panel(**config_options)
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf, "X-Forwarded-For": "203.0.113.9"}
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/game/api/" + endpoint, headers=headers, json={})
    assert response.status_code == 403
    assert api.calls == []


@pytest.mark.parametrize("base_path", ["", "/nb"])
async def test_extension_management_write_is_available_to_local_manager(extension_panel, base_path):
    _, api, base = await extension_panel(base_path=base_path, allow_remote_manage=False)
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/game/api/scores/reset", headers={"X-Token": token, "X-CSRF-Token": csrf}, json={}
        )
    assert response.status_code == 200
    assert api.calls == ["reset_scores"]


async def test_read_only_session_can_read_and_play_without_management(extension_panel):
    _, api, base = await extension_panel(manage_plugins=False, allow_remote_manage=False)
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf, "X-Forwarded-For": "203.0.113.9"}
    async with httpx.AsyncClient() as client:
        scores = await client.get(base + "/game/api/scores", headers=headers)
        submitted = await client.post(base + "/game/api/scores", headers=headers, json={})
        unlocked = await client.post(base + "/game/api/achievements", headers=headers, json={})
    assert [scores.status_code, submitted.status_code, unlocked.status_code] == [200, 200, 200]
    assert api.calls == ["scores", "submit_score", "unlock"]
    assert scores.headers["Cache-Control"] == "no-store"


async def test_legacy_extension_defaults_to_management_for_writes(extension_panel):
    server, _, base = await extension_panel(manage_plugins=False)
    extension = _LegacyExtension()
    server.register_extension("legacy", extension)
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/legacy/api/items", headers=headers)
        write = await client.post(base + "/legacy/api/items", headers=headers, json={})
    assert read.status_code == 200
    assert write.status_code == 403
    assert extension.calls == 1


@pytest.mark.parametrize("permission", [None, "public", "owner", "read"])
async def test_invalid_extension_write_permission_fails_closed(extension_panel, permission):
    server, _, base = await extension_panel()
    extension = _LegacyExtension()
    extension.request_permission = lambda method, path: permission
    server.register_extension("legacy", extension)
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/legacy/api/items", headers={"X-Token": token, "X-CSRF-Token": csrf}, json={}
        )
    assert response.status_code == 403
    assert extension.calls == 0


async def test_extension_permission_error_does_not_reach_handler(extension_panel):
    server, _, base = await extension_panel()
    extension = _LegacyExtension()

    def fail_permission(method, path):
        raise RuntimeError("broken declaration")

    extension.request_permission = fail_permission
    server.register_extension("legacy", extension)
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/legacy/api/items", headers={"X-Token": token, "X-CSRF-Token": csrf}, json={}
        )
    assert response.status_code == 403
    assert extension.calls == 0


async def test_extension_keeps_ip_allow_list_ahead_of_auth(extension_panel):
    _, api, base = await extension_panel(allowed_ips=["198.51.100.0/24"])
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf, "X-Forwarded-For": "203.0.113.9"}
    async with httpx.AsyncClient() as client:
        page = await client.get(base + "/game/", headers=headers)
        write = await client.post(base + "/game/api/scores/reset", headers=headers, json={})
    assert page.status_code == 403
    assert write.status_code == 403
    assert write.json()["allowed_ips"] is False
    assert api.calls == []
