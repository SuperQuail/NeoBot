from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from neobot_contracts.ports.logging import NullLogger
from neobot_app.builtin_plugins.dashboard import server as server_module
from neobot_app.builtin_plugins.dashboard.server import DashboardServer, _bound_access_url


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("0.0.0.0", "http://127.0.0.1:12345/bot/"),
        ("::", "http://[::1]:12345/bot/"),
        ("::1", "http://[::1]:12345/bot/"),
        ("fe80::1234%eth0", "http://[fe80::1234%25eth0]:12345/bot/"),
        ("127.0.0.1", "http://127.0.0.1:12345/bot/"),
        ("192.0.2.1", "http://192.0.2.1:12345/bot/"),
    ],
)
def test_access_url_uses_reachable_host_and_preserves_prefix(host, expected):
    assert _bound_access_url(host, 12345, "/bot") == expected


def make_server(host="127.0.0.1", port=0):
    server = object.__new__(DashboardServer)
    server.config = SimpleNamespace(host=host, port=port)
    server.base_path = "/bot"
    server.logger = NullLogger()
    server.passwords = SimpleNamespace(configured=True)
    server.secure_cookies = True
    server._runner = None
    server._site = None
    server.public_url = None
    server.bound_port = None
    server._make_app = lambda: web.Application()
    server.bilibili_login = SimpleNamespace(close=AsyncMock())
    server.metrics = SimpleNamespace(flush=lambda: None)
    return server


@pytest.mark.asyncio
async def test_ephemeral_port_is_taken_from_actual_bound_socket():
    server = make_server()
    try:
        url = await server.start()
        assert server.bound_port is not None and server.bound_port > 0
        assert url == f"http://127.0.0.1:{server.bound_port}/bot/"
        assert server.connection_info()["local_url"] == url
        assert server.connection_info()["available"] is True
    finally:
        await server.stop()
    assert server.connection_info()["available"] is False
    assert server.connection_info()["local_url"] is None
    assert server.connection_info()["port"] is None


@pytest.mark.asyncio
async def test_last_port_bind_failure_cleans_up_and_never_publishes_a_url(monkeypatch):
    cleanup = AsyncMock()
    runner = SimpleNamespace(setup=AsyncMock(), cleanup=cleanup, addresses=[])
    site = SimpleNamespace(start=AsyncMock(side_effect=OSError("port occupied")))
    monkeypatch.setattr(server_module.web, "AppRunner", lambda *args, **kwargs: runner)
    monkeypatch.setattr(server_module.web, "TCPSite", lambda *args, **kwargs: site)
    server = make_server(port=65535)

    with pytest.raises(OSError, match="未找到可用监听端口"):
        await server.start()

    cleanup.assert_awaited_once()
    assert server.connection_info()["available"] is False
    assert server.bound_port is None
    assert server.public_url is None


@pytest.mark.asyncio
async def test_port_fallback_reports_successfully_bound_port(monkeypatch):
    runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock(), addresses=[("::", 12001, 0, 0)])
    candidates = []

    def site_factory(runner, *, host, port):
        candidates.append(port)
        return SimpleNamespace(start=AsyncMock(side_effect=OSError("occupied") if port == 12000 else None))

    monkeypatch.setattr(server_module.web, "AppRunner", lambda *args, **kwargs: runner)
    monkeypatch.setattr(server_module.web, "TCPSite", site_factory)
    server = make_server(host="::", port=12000)

    assert await server.start() == "http://[::1]:12001/bot/"
    assert candidates == [12000, 12001]
    assert server.bound_port == 12001


@pytest.mark.parametrize(
    ("configured_host", "url_host"),
    [("fe80::1234%eth0", "fe80::1234%25eth0"), ("fe80::1234", "fe80::1234%252")],
)
@pytest.mark.asyncio
async def test_scoped_ipv6_socket_keeps_zone_in_access_url(monkeypatch, configured_host, url_host):
    runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock(), addresses=[("fe80::1234", 12345, 0, 2)])
    site = SimpleNamespace(start=AsyncMock())
    monkeypatch.setattr(server_module.web, "AppRunner", lambda *args, **kwargs: runner)
    monkeypatch.setattr(server_module.web, "TCPSite", lambda *args, **kwargs: site)
    server = make_server(host=configured_host, port=12345)

    assert await server.start() == f"http://[{url_host}]:12345/bot/"
    assert server.connection_info()["local_url"] == f"http://[{url_host}]:12345/bot/"
