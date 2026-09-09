"""官方 dashboard 插件：HTTP 接口与鉴权集成测试。

直接启动真实的 aiohttp 服务（随机端口）并请求，覆盖登录、CSRF、
配置读取/保存与冲突检测、.env 脱敏与插件列表等关键路径。
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore

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
        if action == "get_version_info":
            return {"status": "ok", "data": {"app_name": "NapCat", "app_version": "1.0"}}
        return {"status": "ok", "data": {}}


class _FakeSnapshot:
    def __init__(self, name: str, *, source: str = "third_party") -> None:
        self.name = name
        self.version = "1.0.0"
        self.state = "running"
        self.enabled = True
        self.path = Path("/tmp") / name
        self.kind = "package"
        self.error = None
        self.description = "测试插件"
        self.author = "tester"
        self.dependencies = ()
        self.python_dependencies = ()
        self.missing_python_dependencies = ()
        self.source = source
        self.repo = ""
        self.branch = ""
        self.homepage = ""
        self.license = ""
        self.tags = ()

    @property
    def official(self) -> bool:
        return self.source == "official"

    @property
    def manageable(self) -> bool:
        return not self.official


class _FakeControl:
    def __init__(self) -> None:
        self.snapshots = [
            _FakeSnapshot("dashboard", source="official"),
            _FakeSnapshot("demo"),
        ]
        self.installer_available = True
        self.enabled_calls: list[tuple[str, bool]] = []

    def snapshot(self):
        return list(self.snapshots)

    async def set_enabled(self, name: str, enabled: bool):
        self.enabled_calls.append((name, enabled))
        from neobot_modloader import PluginOperationResult

        return PluginOperationResult(ok=True, name=name, state="running" if enabled else "unloaded")

    async def reload(self, name: str):
        from neobot_modloader import PluginOperationResult

        return PluginOperationResult(ok=True, name=name, state="running")

    async def check_updates(self):
        return []


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_panel(
    tmp_path: Path,
    *,
    password: str | None = PASSWORD,
    trust_proxy: bool = False,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = "0.5.0"\n[dashboard]\nenabled = true\nport = 9981\n', encoding="utf-8"
    )
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-super-secret\n", encoding="utf-8")

    data_dir = tmp_path / "data"
    if password is not None:
        PanelPasswordStore(data_dir / "auth.json").set_password(password)

    control = _FakeControl()
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(
            enabled=True,
            host="127.0.0.1",
            port=_free_port(),
            trust_proxy_headers=trust_proxy,
        ),
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
    return server, control, f"http://127.0.0.1:{server.bound_port}", config_path


@pytest.fixture()
async def panel(tmp_path: Path):
    server, control, base, config_path = await _start_panel(tmp_path)
    try:
        yield server, control, base, config_path
    finally:
        await server.stop()


async def _login(base: str, password: str = PASSWORD) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": password})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["token"], payload["csrf_token"]


async def test_healthz_and_auth_status(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        health = await client.get(base + "/healthz")
        status = await client.get(base + "/api/auth/status")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert status.status_code == 200
    assert status.json()["authenticated"] is False


async def test_login_rejects_wrong_password(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/auth/login", json={"password": "wrong-password"}
        )

    assert response.status_code == 401
    assert response.json()["ok"] is False


async def test_status_reports_password_configured(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/auth/status")

    payload = response.json()
    assert payload["configured"] is True
    assert payload["setup_required"] is False
    assert payload["loopback"] is True


async def test_unconfigured_panel_blocks_external_access(tmp_path: Path) -> None:
    """未设置密码时，外网来源必须被拒绝，且提示设置方式。"""
    server, _, base, _ = await _start_panel(
        tmp_path, password=None, trust_proxy=True
    )
    try:
        headers = {"X-Forwarded-For": "203.0.113.9"}
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/auth/status", headers=headers)
            overview = await client.get(base + "/api/overview", headers=headers)
            login = await client.post(
                base + "/api/auth/login", json={"password": PASSWORD}, headers=headers
            )
            setup = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD},
                headers=headers,
            )

        assert status.json()["loopback"] is False
        assert status.json()["setup_allowed"] is False
        assert overview.status_code == 403
        assert "外网" in overview.json()["error"]
        assert login.status_code == 403
        assert setup.status_code == 403
        assert server.passwords.configured is False
    finally:
        await server.stop()


async def test_unconfigured_panel_allows_loopback_setup(tmp_path: Path) -> None:
    """本机访问未配置密码的面板时，只允许进入设置流程。"""
    server, _, base, _ = await _start_panel(tmp_path, password=None)
    try:
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/auth/status")
            blocked = await client.get(base + "/api/overview")
            weak = await client.post(
                base + "/api/auth/setup", json={"password": "short", "confirm": "short"}
            )
            mismatch = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD + "x"},
            )
            ok = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD},
            )
            overview = await client.get(
                base + "/api/overview", headers={"X-Token": ok.json()["token"]}
            )

        assert status.json()["setup_allowed"] is True
        assert blocked.status_code == 403
        assert blocked.json()["setup_required"] is True
        assert weak.status_code == 400
        assert mismatch.status_code == 400
        assert ok.status_code == 200
        assert server.passwords.verify(PASSWORD) is True
        assert overview.status_code == 200
    finally:
        await server.stop()


async def test_password_change_invalidates_existing_sessions(panel) -> None:
    server, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        before = await client.get(base + "/api/overview", headers={"X-Token": token})
        server.passwords.set_password("NeoBot-Rotated-2026")
        after = await client.get(base + "/api/overview", headers={"X-Token": token})
        relogin = await client.post(
            base + "/api/auth/login", json={"password": "NeoBot-Rotated-2026"}
        )

    assert before.status_code == 200
    assert after.status_code == 401
    assert relogin.status_code == 200


async def test_requires_authentication(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/overview")

    assert response.status_code == 401


async def test_overview_returns_bot_and_stats(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/overview", headers={"X-Token": token})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_nickname"] == "测试机器人"
    assert payload["bot_user_id"] == 10001
    assert payload["app_name"] == "NapCat"
    assert payload["online"] is True


async def test_write_requires_csrf(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        without = await client.post(
            base + "/api/plugins/demo/toggle", headers={"X-Token": token}
        )
        with_token = await client.post(
            base + "/api/plugins/demo/toggle",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
        )

    assert without.status_code == 403
    assert with_token.status_code == 200
    assert with_token.json()["ok"] is True


async def test_plugins_payload_marks_official(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/plugins", headers={"X-Token": token})

    items = {item["name"]: item for item in response.json()["items"]}
    assert items["dashboard"]["official"] is True
    assert items["dashboard"]["manageable"] is False
    assert items["demo"]["official"] is False
    assert response.json()["console_plugin"] == "dashboard"


async def test_config_read_and_save_roundtrip(panel) -> None:
    _, _, base, config_path = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/api/config", headers={"X-Token": token})
        assert read.status_code == 200
        document = read.json()
        assert document["revision"]
        assert document["config"]["dashboard"]["port"] == 9981

        payload = {
            "revision": document["revision"],
            "mode": "form",
            "config": {**document["config"], "dashboard": {**document["config"]["dashboard"], "port": 9999}},
            "reload": False,
        }
        saved = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )

    assert saved.status_code == 200
    assert saved.json()["config"]["dashboard"]["port"] == 9999
    assert 'port = 9999' in config_path.read_text(encoding="utf-8")


async def test_config_save_detects_conflict(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/api/config", headers={"X-Token": token})
        stale = read.json()["revision"]
        payload = {"revision": stale, "mode": "form", "config": read.json()["config"]}
        first = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )
        second = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )

    assert first.status_code == 200
    assert second.status_code == 409


async def test_config_save_rejects_invalid_payload(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"revision": None, "mode": "form", "config": {"dashboard": {"port": "abc"}}},
        )

    assert response.status_code == 400
    assert response.json()["errors"]


async def test_env_masks_secret_and_reveals_on_request(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/env", headers={"X-Token": token})
        revealed = await client.get(
            base + "/api/config/env/DeepSeek_APIKey/value", headers={"X-Token": token}
        )

    items = {item["key"]: item for item in listed.json()["items"]}
    assert items["DeepSeek_APIKey"]["value"] != "sk-super-secret"
    assert items["DeepSeek_APIKey"]["masked"] is True
    assert revealed.json()["value"] == "sk-super-secret"


async def test_env_save_updates_file(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/env", headers={"X-Token": token})
        response = await client.post(
            base + "/api/config/env",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "revision": listed.json()["revision"],
                "updates": {"MyProvider_URL": "https://example.com/v1"},
                "deletes": [],
            },
        )

    assert response.status_code == 200
    assert "MyProvider_URL=https://example.com/v1" in panel[0].env_manager.env_path.read_text(encoding="utf-8")


async def test_logs_endpoint_shape(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/logs", headers={"X-Token": token})

    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["items"], list)
    assert "last_id" in payload
