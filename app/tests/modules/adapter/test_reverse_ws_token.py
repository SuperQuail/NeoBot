"""反向 WebSocket 握手鉴权（OneBot 11 access token）测试。

规范依据（OneBot 11「鉴权」章节）：填写了 access token 时，OneBot 的反向
WebSocket **客户端**在建立连接时会在请求头中加入 ``Authorization: Bearer
<access_token>``；本端作为反向 WS 服务端负责校验。
"""

from __future__ import annotations

from typing import Any

import pytest
import websockets

from neobot_adapter.onebot.receiver.core import (
    AdapterCore,
    _extract_access_token,
)
from neobot_adapter.utils.net import is_loopback_host


class _FakeConnection:
    """新版 websockets API 的 connection 替身：只记录 respond()。"""

    def __init__(self) -> None:
        self.responded: tuple[Any, str] | None = None

    def respond(self, status: Any, text: str = "") -> str:
        self.responded = (status, text)
        return "response-sentinel"


class _FakeRequest:
    def __init__(self, headers: dict[str, str], path: str = "/onebot") -> None:
        self.headers = headers
        self.path = path


# ── _extract_access_token ────────────────────────────────────────────


def test_extract_token_from_bearer_header() -> None:
    headers = {"Authorization": "Bearer kSLuTF2GC2Q4q4ugm3"}
    assert _extract_access_token(headers, "/onebot") == "kSLuTF2GC2Q4q4ugm3"


def test_extract_token_accepts_bare_header_value() -> None:
    """部分框架只填 token、不带 Bearer 前缀，宽容接受。"""
    assert _extract_access_token({"Authorization": "plain-token"}, "/") == "plain-token"


def test_extract_token_from_query_parameter() -> None:
    """规范对 HTTP / 正向 WS 给出的 query 兜底形式，这里同样兼容。"""
    assert (
        _extract_access_token({}, "/onebot?access_token=q-token&x=1") == "q-token"
    )


def test_extract_token_missing_returns_none() -> None:
    assert _extract_access_token({}, "/onebot") is None
    assert _extract_access_token(None, "/onebot") is None


def test_extract_token_header_takes_precedence_over_query() -> None:
    headers = {"Authorization": "Bearer from-header"}
    assert _extract_access_token(headers, "/onebot?access_token=from-query") == (
        "from-header"
    )


# ── 握手鉴权：配置了 token ───────────────────────────────────────────


async def test_handshake_allows_matching_token_new_api() -> None:
    core = AdapterCore(access_token="s3cret")
    connection = _FakeConnection()
    result = await core._authorize_handshake(
        connection, _FakeRequest({"Authorization": "Bearer s3cret"})
    )
    assert result is None
    assert connection.responded is None


async def test_handshake_rejects_wrong_token_new_api() -> None:
    core = AdapterCore(access_token="s3cret")
    connection = _FakeConnection()
    result = await core._authorize_handshake(
        connection, _FakeRequest({"Authorization": "Bearer nope"})
    )
    assert result == "response-sentinel"
    assert connection.responded is not None
    assert int(connection.responded[0]) == 401


async def test_handshake_rejects_missing_token_new_api() -> None:
    core = AdapterCore(access_token="s3cret")
    connection = _FakeConnection()
    result = await core._authorize_handshake(connection, _FakeRequest({}))
    assert result == "response-sentinel"
    assert int(connection.responded[0]) == 401


async def test_handshake_accepts_query_token_new_api() -> None:
    core = AdapterCore(access_token="s3cret")
    connection = _FakeConnection()
    result = await core._authorize_handshake(
        connection, _FakeRequest({}, path="/onebot?access_token=s3cret")
    )
    assert result is None
    assert connection.responded is None


# ── 握手鉴权：未配置 token（历史行为保持） ──────────────────────────


async def test_handshake_allows_everything_without_token() -> None:
    core = AdapterCore()
    connection = _FakeConnection()
    result = await core._authorize_handshake(connection, _FakeRequest({}))
    assert result is None
    assert connection.responded is None


# ── 兼容旧版 websockets API 的签名 ──────────────────────────────────


async def test_handshake_legacy_signature_rejects() -> None:
    core = AdapterCore(access_token="s3cret")
    status, _headers, _body = await core._authorize_handshake(
        "/onebot", {"Authorization": "Bearer nope"}
    )
    assert int(status) == 401


async def test_handshake_legacy_signature_allows() -> None:
    core = AdapterCore(access_token="s3cret")
    assert await core._authorize_handshake(
        "/onebot", {"Authorization": "Bearer s3cret"}
    ) is None


# ── 回环判定（决定启动告警） ────────────────────────────────────────


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.0.0.53", True),
        ("localhost", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("", False),
    ],
)
def test_is_loopback_host(host: str, expected: bool) -> None:
    assert is_loopback_host(host) is expected


# ── 端到端：真实 websockets 握手 ─────────────────────────────────────


async def _serve_once(core: AdapterCore):
    """用真实的 websockets 服务端挂上鉴权钩子，返回 (server, port)。"""

    async def _handler(websocket: Any) -> None:
        # 保持连接直到客户端主动关闭，便于断言握手后的连接状态
        await websocket.wait_closed()

    server = await websockets.serve(
        _handler,
        "127.0.0.1",
        0,
        process_request=core._authorize_handshake,
    )
    port = int(server.sockets[0].getsockname()[1])
    return server, port


async def test_real_handshake_rejects_wrong_token() -> None:
    core = AdapterCore(access_token="s3cret")
    server, port = await _serve_once(core)
    try:
        with pytest.raises(websockets.exceptions.InvalidStatus) as excinfo:
            async with websockets.connect(
                f"ws://127.0.0.1:{port}/onebot",
                additional_headers={"Authorization": "Bearer nope"},
            ):
                pass
        assert excinfo.value.response.status_code == 401
    finally:
        server.close()
        await server.wait_closed()


async def test_real_handshake_accepts_matching_token() -> None:
    core = AdapterCore(access_token="s3cret")
    server, port = await _serve_once(core)
    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/onebot",
            additional_headers={"Authorization": "Bearer s3cret"},
        ) as websocket:
            assert websocket.state.name == "OPEN"
    finally:
        server.close()
        await server.wait_closed()


async def test_real_handshake_rejects_when_token_expected_but_absent() -> None:
    core = AdapterCore(access_token="s3cret")
    server, port = await _serve_once(core)
    try:
        with pytest.raises(websockets.exceptions.InvalidStatus) as excinfo:
            async with websockets.connect(f"ws://127.0.0.1:{port}/onebot"):
                pass
        assert excinfo.value.response.status_code == 401
    finally:
        server.close()
        await server.wait_closed()


async def test_real_handshake_open_when_no_token_configured() -> None:
    """未配置 token 时保持历史行为：任何来源都能连上。"""
    core = AdapterCore()
    server, port = await _serve_once(core)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/onebot") as websocket:
            assert websocket.state.name == "OPEN"
    finally:
        server.close()
        await server.wait_closed()
