"""隔离 HTTP 服务验证面板对所有爬虫的抓取/索引声明。"""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from neobot_app.builtin_plugins.dashboard import server as server_module
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer

PASSWORD = "NeoBot-Panel-2026"
ROBOTS = "User-agent: *\nDisallow: /\n"
POLICY = "noindex, nofollow, nosnippet, noimageindex"


def test_static_robots_source_matches_backend_rules():
    frontend = Path(server_module.__file__).with_name("frontend")
    assert (frontend / "public" / "robots.txt").read_text(encoding="utf-8") == ROBOTS


def test_static_entry_declares_backend_indexing_policy_in_head():
    class MetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_head = False
            self.policies: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag == "head":
                self.in_head = True
            attributes = dict(attrs)
            if self.in_head and tag == "meta" and attributes.get("name", "").lower() == "robots":
                self.policies.append(attributes.get("content", ""))

        def handle_endtag(self, tag):
            if tag == "head":
                self.in_head = False

    frontend = Path(server_module.__file__).with_name("frontend")
    parser = MetaParser()
    parser.feed((frontend / "index.html").read_text(encoding="utf-8"))
    assert len(parser.policies) == 1
    assert {item.strip().lower() for item in parser.policies[0].split(",")} == set(POLICY.split(", "))


class _ProbeExtension:
    prefixes = ("/probe",)
    auth_prefixes = ("/probe/private", "/robots.txt")

    async def handle_request(self, request, path):
        if path == "/probe/failure":
            raise RuntimeError("isolated extension failure")
        if path == "/probe/redirect":
            raise web.HTTPFound(location="/probe/page")
        if path == "/probe/stream":
            response = web.StreamResponse(headers={"X-Robots-Tag": "all"})
            await response.prepare(request)
            await response.write(b"streamed extension response")
            await response.write_eof()
            return response
        return web.Response(text="extension", headers={"X-Robots-Tag": "all"})


@pytest.fixture
async def panel_factory(tmp_path: Path, monkeypatch):
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<!doctype html><title>Isolated panel</title>", encoding="utf-8")
    (static_dir / "assets" / "example.js").write_text("export const example = true;", encoding="utf-8")
    monkeypatch.setattr(server_module, "_STATIC_DIR", static_dir)
    monkeypatch.setattr(server_module, "_INDEX_FILE", static_dir / "index.html")
    clients: list[TestClient] = []

    async def create(*, base_path="", configured=True):
        root = tmp_path / f"panel-{len(clients)}"
        server = DashboardServer(
            plugin_name="dashboard",
            config=DashboardConfig(base_path=base_path, trust_proxy_headers=True),
            data_dir=root / "data",
            logger=logging.getLogger(__name__),
            config_path=root / "config.toml",
            env_path=root / ".env",
            backup_dir=root / "backup",
        )
        if configured:
            server.passwords.set_password(PASSWORD)
        server.register_extension("probe", _ProbeExtension())
        client = TestClient(TestServer(server._make_app()))
        clients.append(client)
        await client.start_server()
        return server, client

    yield create
    for client in clients:
        await client.close()


@pytest.mark.parametrize("base_path", ["", "/panel", "/robots"])
@pytest.mark.parametrize("configured", [False, True])
async def test_robots_get_head_are_public_at_root_and_base_path(panel_factory, base_path, configured):
    _, client = await panel_factory(base_path=base_path, configured=configured)
    headers = {"X-Forwarded-For": "203.0.113.9", "User-Agent": "Googlebot/2.1"}
    for path in dict.fromkeys(["/robots.txt", base_path + "/robots.txt"]):
        response = await client.get(path, headers=headers)
        assert response.status == 200
        assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
        assert response.headers["X-Robots-Tag"] == POLICY
        assert response.headers["Cache-Control"] == "no-store"
        assert await response.text() == ROBOTS
        head = await client.head(path, headers=headers)
        assert head.status == 200
        assert head.headers["Content-Type"] == response.headers["Content-Type"]
        assert head.headers["Content-Length"] == str(len(ROBOTS.encode("utf-8")))
        assert head.headers["X-Robots-Tag"] == POLICY
        assert await head.read() == b""


@pytest.mark.parametrize("base_path", ["", "/panel"])
async def test_robots_header_covers_static_errors_redirects_and_extensions(panel_factory, base_path):
    _, client = await panel_factory(base_path=base_path)
    cases = [
        ("/", 200),
        ("/healthz", 200),
        ("/assets/example.js", 200),
        ("/assets/missing.js", 404),
        ("/bilibili/login", 200),
        ("/bilibili/login.js", 200),
        ("/api/auth/me", 401),
        ("/probe/page", 200),
        ("/probe/private", 401),
        ("/probe/failure", 500),
        ("/probe/redirect", 302),
        ("/probe/stream", 200),
    ]
    for path, expected in cases:
        response = await client.get(base_path + path, allow_redirects=False)
        assert response.status == expected, path
        assert response.headers.getall("X-Robots-Tag") == [POLICY], path
        await response.read()
    asset = await client.get(base_path + "/assets/example.js")
    await asset.read()
    cached = await client.get(base_path + "/assets/example.js", headers={"If-None-Match": asset.headers["ETag"]})
    assert cached.status == 304
    assert cached.headers["X-Robots-Tag"] == POLICY


@pytest.mark.parametrize("agent", ["Mozilla/5.0", "Googlebot/2.1", "ExampleCrawler/1.0"])
async def test_robots_policy_does_not_change_authentication_or_block_user_agents(panel_factory, agent):
    _, client = await panel_factory()
    headers = {"User-Agent": agent}
    page = await client.get("/", headers=headers)
    assert page.status == 200
    anonymous = await client.get("/api/auth/me", headers=headers)
    assert anonymous.status == 401
    login = await client.post("/api/auth/login", headers=headers, json={"password": PASSWORD})
    assert login.status == 200
    assert login.headers["X-Robots-Tag"] == POLICY
    session = await login.json()
    authenticated = await client.get("/api/auth/me", headers={**headers, "X-Token": session["token"]})
    assert authenticated.status == 200
    assert authenticated.headers["X-Robots-Tag"] == POLICY
    forbidden_write = await client.post("/api/auth/password", headers={**headers, "X-Token": session["token"]}, json={})
    assert forbidden_write.status == 403
    assert forbidden_write.headers["X-Robots-Tag"] == POLICY
