"""面板 IP 白名单：配置校验与真实 HTTP 请求。"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import tomllib

from aiohttp.test_utils import TestClient, TestServer
import pytest
from pydantic import ValidationError

from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard import config as config_module
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.hot_reload import DashboardConfigConsumer
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.runtime.plugin_config_reload import classify_plugin_path


@asynccontextmanager
async def _panel(tmp_path, *, configured=True, **config):
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(**config),
        data_dir=tmp_path / "dashboard",
        logger=logging.getLogger(__name__),
        config_path=tmp_path / "config.toml",
        env_path=tmp_path / ".env",
        backup_dir=tmp_path / "backup",
    )
    if configured:
        server.passwords.set_password("Panel-test-password")
    async with TestClient(TestServer(server._make_app())) as client:
        yield server, client


@pytest.mark.parametrize("value", [["localhost"], ["192.0.2.0/24"], ["999.0.0.1"], [""], [123], "127.0.0.1", None])
def test_invalid_allowed_ips_rejected(value):
    with pytest.raises(ValidationError):
        DashboardConfig(allowed_ips=value)


def test_manifest_and_model_default_allowlist_match():
    manifest = Path(config_module.__file__).with_name("plugin.toml")
    defaults = tomllib.loads(manifest.read_text(encoding="utf-8"))["config"]
    assert defaults["allowed_ips"] == []
    assert DashboardConfig().allowed_ips == []
    assert DashboardConfig(**defaults).allowed_ips == []


@pytest.mark.parametrize("config", [{}, {"allowed_ips": []}])
async def test_empty_or_absent_allowlist_preserves_access(tmp_path, config):
    async with _panel(tmp_path, trust_proxy_headers=True, **config) as (_, client):
        response = await client.get("/healthz", headers={"X-Forwarded-For": "192.0.2.20"})
        assert response.status == 200
        assert (await response.json())["ok"] is True


@pytest.mark.parametrize(
    ("allowed", "source"),
    [
        (["127.0.0.1"], "127.0.0.1"),
        (["::1"], "0:0:0:0:0:0:0:1"),
        ([" 2001:0DB8:0:0::1 "], "2001:db8::1"),
        (["192.0.2.20"], "192.0.2.20"),
        (["192.0.2.20"], "::ffff:192.0.2.20"),
        (["::ffff:c000:214"], "192.0.2.20"),
    ],
)
async def test_matching_ips_allowed(tmp_path, allowed, source):
    async with _panel(tmp_path, allowed_ips=allowed, trust_proxy_headers=True) as (_, client):
        response = await client.get("/healthz", headers={"X-Forwarded-For": source})
        assert response.status == 200


@pytest.mark.parametrize("configured", [True, False])
@pytest.mark.parametrize("prefix", ["", "/neobot"])
async def test_denied_ip_cannot_access_any_route(tmp_path, configured, prefix):
    async with _panel(tmp_path, configured=configured, allowed_ips=["192.0.2.20"], base_path=prefix) as (_, client):
        for path in (
            "/",
            "/assets/missing.js",
            "/image/missing.png",
            "/healthz",
            "/game/",
            "/api/auth/status",
            "/api/overview",
        ):
            response = await client.get(prefix + path)
            assert response.status == 403, path
            assert (await response.json())["error"] == "当前 IP 不允许访问面板"
        for path in ("/api/auth/login", "/api/auth/setup"):
            response = await client.post(prefix + path, json={"password": "Panel-test-password"})
            assert response.status == 403, path
            assert (await response.json())["error"] == "当前 IP 不允许访问面板"


@pytest.mark.parametrize("source", ["192.0.2.21", "::1", "127.0.0.1", "127.invalid", "unknown", "192.0.2.20:123"])
async def test_unlisted_or_invalid_source_rejected(tmp_path, source):
    async with _panel(tmp_path, allowed_ips=["192.0.2.20"], trust_proxy_headers=True) as (_, client):
        response = await client.get("/healthz", headers={"X-Forwarded-For": source})
        assert response.status == 403


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP"])
async def test_untrusted_forwarded_headers_cannot_bypass_allowlist(tmp_path, header):
    async with _panel(tmp_path, allowed_ips=["192.0.2.20"]) as (_, client):
        response = await client.get("/healthz", headers={header: "192.0.2.20"})
        assert response.status == 403


async def test_loopback_peer_allowed_without_trusting_headers(tmp_path):
    async with _panel(tmp_path, allowed_ips=["127.0.0.1"]) as (_, client):
        response = await client.get("/healthz", headers={"X-Forwarded-For": "192.0.2.20"})
        assert response.status == 200


async def test_trusted_proxy_uses_last_forwarded_address(tmp_path):
    async with _panel(tmp_path, allowed_ips=["192.0.2.20"], trust_proxy_headers=True) as (_, client):
        response = await client.get("/healthz", headers={"X-Forwarded-For": "192.0.2.20, 192.0.2.21"})
        assert response.status == 403
        response = await client.get("/healthz", headers={"X-Real-IP": "192.0.2.20"})
        assert response.status == 200


async def test_allowed_ip_still_requires_login(tmp_path):
    async with _panel(tmp_path, allowed_ips=["127.0.0.1"]) as (_, client):
        response = await client.get("/api/overview")
        assert response.status == 401
        login = await client.post("/api/auth/login", json={"password": "Panel-test-password"})
        assert login.status == 200
        token = (await login.json())["token"]
        response = await client.get("/api/overview", headers={"X-Token": token})
        assert response.status == 200


async def test_valid_session_cannot_bypass_allowlist(tmp_path):
    async with _panel(tmp_path, allowed_ips=["192.0.2.20"], trust_proxy_headers=True) as (_, client):
        login = await client.post(
            "/api/auth/login", json={"password": "Panel-test-password"}, headers={"X-Forwarded-For": "192.0.2.20"}
        )
        assert login.status == 200
        token = (await login.json())["token"]
        response = await client.get("/api/overview", headers={"X-Token": token, "X-Forwarded-For": "192.0.2.21"})
        assert response.status == 403


async def test_allowlist_changes_wait_for_restart(tmp_path):
    consumer = DashboardConfigConsumer(DashboardPlugin())
    hot, reason = classify_plugin_path(consumer, "plugin.dashboard.allowed_ips")
    assert hot is False
    assert "未声明" not in reason
    async with _panel(tmp_path, allowed_ips=["192.0.2.20"]) as (server, client):
        server.apply_runtime_config(DashboardConfig(allowed_ips=[]))
        response = await client.get("/healthz")
        assert response.status == 403


@pytest.mark.parametrize("text", ['allowed_ips = ["invalid"]', 'allowed_ips = "127.0.0.1"', "allowed_ips = ["])
async def test_invalid_stored_allowlist_cannot_fall_back_to_unrestricted(tmp_path, text):
    data_dir = tmp_path / "dashboard"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        async with _panel(tmp_path):
            pytest.fail("非法白名单不应启动面板")


async def test_stored_allowlist_survives_host_config_fallback(tmp_path):
    data_dir = tmp_path / "dashboard"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text('allowed_ips = ["192.0.2.20"]\nport = "invalid"', encoding="utf-8")
    async with _panel(tmp_path) as (_, client):
        response = await client.get("/healthz")
        assert response.status == 403
