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


@pytest.fixture()
async def panel(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'version = "0.5.0"\n[dashboard]\nenabled = true\nport = 9981\n', encoding="utf-8"
    )
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-super-secret\n", encoding="utf-8")

    control = _FakeControl()
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(
            enabled=True, host="127.0.0.1", port=_free_port(), access_token="test-token"
        ),
        data_dir=tmp_path / "data",
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=control,
        services=None,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    base = f"http://127.0.0.1:{server.bound_port}"
    try:
        yield server, control, base, config_path
    finally:
        await server.stop()


async def _login(base: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/auth/login", json={"access_token": "test-token"}
        )
    assert response.status_code == 200
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


async def test_login_rejects_wrong_token(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/auth/login", json={"access_token": "wrong"}
        )

    assert response.status_code == 401
    assert response.json()["ok"] is False


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
