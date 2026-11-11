"""官方 WebSocket 网关测试。

用假 aiohttp 与假 WebSocket 驱动协议：Hello -> Identify/Resume、心跳、close
code 分类（含不可重试码）、op7/op9 重连语义、dispatch 原样回调。不联网。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_adapter.official import gateway as gateway_module
from neobot_adapter.official.auth import OfficialAuthError, OfficialNetworkError
from neobot_adapter.official.gateway import OfficialGateway
from neobot_adapter.official.settings import OfficialSettings

_STOP = object()


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakeHttp:
    def __init__(self, *, status: int = 200, payload: Any = None) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._status = status
        self._payload = payload if payload is not None else {"url": "wss://gateway.example/ws"}

    def get(self, url: str, headers: Any = None) -> FakeResponse:
        self.requests.append((url, dict(headers or {})))
        return FakeResponse(self._status, self._payload)


class FakeTokenProvider:
    def __init__(self, token: str = "tok") -> None:
        self.token = token
        self.invalidated = 0

    async def get_token(self, *, force: bool = False) -> str:
        return self.token

    def invalidate(self) -> None:
        self.invalidated += 1


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.closed = False

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def __aiter__(self) -> "FakeWS":
        return self

    async def __anext__(self) -> str:
        item = await self.incoming.get()
        if item is _STOP:
            raise StopAsyncIteration
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item)

    async def close(self) -> None:
        self.closed = True


class FakeLogger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, Any]]] = []
        self.warnings: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, dict[str, Any]]] = []
        self.debugs: list[tuple[str, dict[str, Any]]] = []

    def bind(self, **ctx: Any) -> "FakeLogger":
        return self

    def debug(self, msg: str, **kw: Any) -> None:
        self.debugs.append((msg, kw))

    def info(self, msg: str, **kw: Any) -> None:
        self.infos.append((msg, kw))

    def warning(self, msg: str, **kw: Any) -> None:
        self.warnings.append((msg, kw))

    def error(self, msg: str, **kw: Any) -> None:
        self.errors.append((msg, kw))

    def exception(self, msg: str, **kw: Any) -> None:
        self.errors.append((msg, kw))


def _frame(
    op: int,
    data: Any = None,
    *,
    event_type: str | None = None,
    seq: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"op": op, "d": data}
    if event_type is not None:
        payload["t"] = event_type
        payload["id"] = "event-id"
    if seq is not None:
        payload["s"] = seq
    return payload


def _make_gateway(
    work_dir: Path,
    *,
    ws: FakeWS | None = None,
    http: FakeHttp | None = None,
    token: FakeTokenProvider | None = None,
    on_event: Any = None,
    logger: FakeLogger | None = None,
    on_auth_exhausted: Any = None,
) -> tuple[OfficialGateway, FakeWS, FakeHttp, list[str]]:
    fake_ws = ws if ws is not None else FakeWS()
    fake_http = http if http is not None else FakeHttp()
    fake_token = token if token is not None else FakeTokenProvider()
    urls: list[str] = []

    async def connect(url: str) -> FakeWS:
        urls.append(url)
        return fake_ws

    gateway = OfficialGateway(
        OfficialSettings(app_id="app", client_secret="secret", data_dir=work_dir),
        fake_token,
        on_event if on_event is not None else (lambda payload: None),
        logger if logger is not None else FakeLogger(),
        http=fake_http,
        ws_connect=connect,
        on_auth_exhausted=on_auth_exhausted,
    )
    return gateway, fake_ws, fake_http, urls


async def _wait_for(predicate: Any, timeout: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return False


def _ops(ws: FakeWS, op: int) -> list[dict[str, Any]]:
    return [payload for payload in ws.sent if payload.get("op") == op]


# ── 连接与 Identify / Resume ────────────────────────────────────────


async def test_gateway_identifies_and_emits_ready(workdir: Path) -> None:
    events: list[dict[str, Any]] = []
    gateway, ws, http, urls = _make_gateway(workdir, on_event=events.append)

    await gateway.start()
    ws.incoming.put_nowait(_frame(10, {"heartbeat_interval": 60_000}))
    ready = _frame(0, {"session_id": "sess-1"}, event_type="READY", seq=1)
    ws.incoming.put_nowait(ready)
    assert await gateway.wait_connected(2.0)
    assert gateway.connected

    assert urls == ["wss://gateway.example/ws"]
    assert http.requests == [
        ("https://api.bot.qq.com/gateway", {"Authorization": "QQBot tok", "Accept": "application/json"})
    ]
    identify = _ops(ws, 2)
    assert identify == [
        {
            "op": 2,
            "d": {"token": "QQBot tok", "intents": (1 << 25) | (1 << 24), "shard": [0, 1]},
        }
    ]

    assert await _wait_for(lambda: events)
    assert events[0]["op"] == 0
    assert events[0]["t"] == "READY"
    assert events[0]["d"]["session_id"] == "sess-1"
    assert gateway._session_id == "sess-1"

    await gateway.stop()
    assert ws.closed
    assert not gateway.connected


async def test_gateway_resumes_existing_session_on_hello(workdir: Path) -> None:
    gateway, ws, _http, _urls = _make_gateway(workdir)
    gateway._session_id = "sess-9"
    gateway._last_seq = 42

    await gateway.start()
    ws.incoming.put_nowait(_frame(10, {"heartbeat_interval": 60_000}))

    assert await _wait_for(lambda: ws.sent)
    assert _ops(ws, 6) == [
        {
            "op": 6,
            "d": {"token": "QQBot tok", "session_id": "sess-9", "seq": 42},
        }
    ]
    assert _ops(ws, 2) == []
    await gateway.stop()


async def test_gateway_heartbeats_with_last_seq(workdir: Path) -> None:
    gateway, ws, _http, _urls = _make_gateway(workdir)
    await gateway.start()
    ws.incoming.put_nowait(_frame(10, {"heartbeat_interval": 40}))
    assert await _wait_for(lambda: ws.sent)
    ws.incoming.put_nowait(_frame(0, {}, event_type="C2C_MESSAGE_CREATE", seq=7))

    assert await _wait_for(lambda: any(item.get("d") == 7 for item in _ops(ws, 1)))
    await gateway.stop()


# ── close code 分类与重连动作 ───────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "action"),
    [
        (4914, "fatal"),
        (4915, "fatal"),
        (4004, "token"),
        (4006, "session"),
        (4007, "session"),
        (4009, "session"),
        (4008, "retry"),
        (1000, "retry"),
        (None, "retry"),
    ],
)
def test_gateway_classifies_close_codes(workdir: Path, code: int | None, action: str) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)
    assert gateway._classify_close(code) == action


def test_gateway_backoff_grows_and_is_capped(workdir: Path) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)

    first = gateway._backoff_delay(0)
    later = gateway._backoff_delay(5)

    assert 0.5 <= first <= 1.0
    assert 16.0 <= later <= 32.0
    assert first <= later


async def test_gateway_invalidates_token_on_4004(workdir: Path) -> None:
    token = FakeTokenProvider()
    gateway, _ws, _http, _urls = _make_gateway(workdir, token=token)
    gateway._session_id = "stale-session"
    gateway._last_seq = 9
    calls: list[int] = []

    async def failing_connect() -> None:
        calls.append(1)
        raise gateway_module._GatewayClosed(4004, "invalid token")

    gateway._connect_once = failing_connect
    gateway._backoff_delay = lambda attempt: 0.01

    await gateway.start()
    assert await _wait_for(lambda: token.invalidated)
    assert await _wait_for(lambda: gateway._session_id == "")
    await gateway.stop()
    assert calls


async def test_gateway_clears_session_on_4006(workdir: Path) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)
    gateway._session_id = "sess-1"
    gateway._last_seq = 3

    async def failing_connect() -> None:
        raise gateway_module._GatewayClosed(4006, "invalid session")

    gateway._connect_once = failing_connect
    gateway._backoff_delay = lambda attempt: 0.01

    await gateway.start()
    assert await _wait_for(lambda: gateway._session_id == "")
    assert gateway._last_seq is None
    await gateway.stop()


async def test_gateway_stops_retrying_on_fatal_close(workdir: Path) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)
    calls: list[int] = []

    async def failing_connect() -> None:
        calls.append(1)
        raise gateway_module._GatewayClosed(4914, "bot offline")

    gateway._connect_once = failing_connect
    gateway._backoff_delay = lambda attempt: 0.0

    await gateway.start()
    task = gateway._task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 2.0)

    assert calls == [1]
    assert not gateway.connected
    errors = [message for message, _kw in gateway._logger.errors]
    assert any("停止重连" in message for message in errors)
    await gateway.stop()


@pytest.mark.parametrize(("op", "clear_session"), [(7, False), (9, True)])
async def test_gateway_op7_and_op9_raise_reconnect(workdir: Path, op: int, clear_session: bool) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)

    with pytest.raises(gateway_module._Reconnect) as excinfo:
        await gateway._handle_frame(SimpleNamespace(), json.dumps(_frame(op)))

    assert excinfo.value.clear_session is clear_session


# ── 连续登录/鉴权失败 ──────────────────────────────────────────────


async def test_gateway_requires_relogin_after_three_auth_failures(workdir: Path) -> None:
    """token 获取失败与 4004 都算登录失败；第 3 次后停止重连并交给上层。"""
    exhausted: list[int] = []
    logger = FakeLogger()
    gateway, _ws, _http, _urls = _make_gateway(
        workdir, logger=logger, on_auth_exhausted=lambda: exhausted.append(1)
    )
    attempts: list[int] = []

    async def failing_connect() -> None:
        attempts.append(1)
        if len(attempts) == 2:
            raise gateway_module._GatewayClosed(4004, "invalid token")
        raise OfficialAuthError("获取官方网关地址失败：HTTP 401")

    gateway._connect_once = failing_connect
    gateway._backoff_delay = lambda attempt: 0.0

    await gateway.start()
    task = gateway._task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 2.0)

    assert len(attempts) == 3
    assert exhausted == [1]
    assert not gateway.connected
    assert any("连续 3 次登录失败" in message for message, _kw in logger.errors)
    await gateway.stop()


@pytest.mark.parametrize("event_type", ["READY", "RESUMED"])
async def test_gateway_auth_failure_count_resets_on_ready_or_resumed(
    workdir: Path, event_type: str
) -> None:
    """就绪过（READY/RESUMED）即清零：失败两次、就绪、再失败三次才耗尽。"""
    exhausted: list[int] = []
    gateway, _ws, _http, _urls = _make_gateway(
        workdir, on_auth_exhausted=lambda: exhausted.append(1)
    )
    attempts: list[int] = []

    async def scripted_connect() -> None:
        attempts.append(1)
        if len(attempts) == 3:
            gateway._track_dispatch(
                {"t": event_type, "d": {"session_id": "s-1"}},
                {"session_id": "s-1"},
            )
            raise gateway_module._GatewayClosed(1000, "normal close")
        raise OfficialAuthError("token 失效")

    gateway._connect_once = scripted_connect
    gateway._backoff_delay = lambda attempt: 0.0

    await gateway.start()
    task = gateway._task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 2.0)

    assert len(attempts) == 6
    assert exhausted == [1]
    await gateway.stop()


async def test_gateway_network_errors_do_not_count_as_auth_failures(
    workdir: Path,
) -> None:
    """token/网关地址请求的网络层失败只是断网，不能当凭据失效。"""
    exhausted: list[int] = []
    gateway, _ws, _http, _urls = _make_gateway(
        workdir, on_auth_exhausted=lambda: exhausted.append(1)
    )
    attempts: list[int] = []

    async def offline_connect() -> None:
        attempts.append(1)
        if len(attempts) >= 3:
            gateway._stopping.set()
        raise OfficialNetworkError("请求官方接口失败: ClientConnectorError")

    gateway._connect_once = offline_connect
    gateway._backoff_delay = lambda attempt: 0.0

    await gateway.start()
    task = gateway._task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 2.0)

    assert len(attempts) == 3
    assert gateway._auth_failures == 0
    assert exhausted == []


async def test_gateway_network_closes_do_not_count_as_auth_failures(
    workdir: Path,
) -> None:
    """普通断线、会话失效、限频退避都不算登录失败，不触发重新扫码。"""
    exhausted: list[int] = []
    gateway, _ws, _http, _urls = _make_gateway(
        workdir, on_auth_exhausted=lambda: exhausted.append(1)
    )
    codes = [4006, 4008, 1000]
    attempts: list[int] = []

    async def flaky_connect() -> None:
        attempts.append(1)
        code = codes[len(attempts) - 1]
        if len(attempts) >= len(codes):
            gateway._stopping.set()
        raise gateway_module._GatewayClosed(code, "network")

    gateway._connect_once = flaky_connect
    gateway._backoff_delay = lambda attempt: 0.0

    await gateway.start()
    task = gateway._task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), 2.0)

    assert len(attempts) == 3
    assert gateway._auth_failures == 0
    assert exhausted == []


# ── 事件回调与停止 ──────────────────────────────────────────────────


async def test_gateway_event_handler_errors_are_isolated(workdir: Path) -> None:
    seen: list[str] = []
    logger = FakeLogger()

    async def handler(payload: dict[str, Any]) -> None:
        seen.append(str(payload.get("t")))
        raise RuntimeError("handler boom")

    gateway, ws, _http, _urls = _make_gateway(workdir, on_event=handler, logger=logger)
    await gateway.start()
    ws.incoming.put_nowait(_frame(10, {"heartbeat_interval": 60_000}))
    ws.incoming.put_nowait(_frame(0, {}, event_type="C2C_MESSAGE_CREATE"))
    ws.incoming.put_nowait(_frame(0, {}, event_type="GROUP_AT_MESSAGE_CREATE"))

    assert await _wait_for(lambda: len(seen) == 2)
    assert gateway._task is not None and not gateway._task.done()
    assert logger.errors
    await gateway.stop()


async def test_gateway_wait_connected_times_out_and_stop_is_idempotent(
    workdir: Path,
) -> None:
    gateway, _ws, _http, _urls = _make_gateway(workdir)

    assert await gateway.wait_connected(0.01) is False

    await gateway.stop()
    await gateway.stop()
    assert not gateway.connected


async def test_gateway_clears_connected_when_connection_ends(workdir: Path) -> None:
    """连接结束后立即不可用，重连退避期间不能继续按 connected 选路。"""
    gateway, ws, _http, _urls = _make_gateway(workdir)
    await gateway.start()
    ws.incoming.put_nowait(_frame(10, {"heartbeat_interval": 60_000}))
    ws.incoming.put_nowait(_frame(0, {"session_id": "sess-1"}, event_type="READY"))
    assert await gateway.wait_connected(2.0)
    assert gateway.connected

    ws.incoming.put_nowait(_STOP)
    assert await _wait_for(lambda: not gateway.connected)
    await gateway.stop()
