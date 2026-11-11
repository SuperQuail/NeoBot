"""官方鉴权核心测试。

覆盖：AdapterSettings -> OfficialSettings 解析、凭据 0600 原子落盘、access
token 的 80% 缓存/单飞刷新/强制刷新、扫码绑定的 create/poll/过期重建/AES-GCM
解密，全部使用假 aiohttp 会话，不联网。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from neobot_adapter.official import auth
from neobot_adapter.official.auth import (
    BindState,
    CredentialStore,
    Credentials,
    OfficialAuthError,
    QrBindFlow,
    TokenProvider,
    decrypt_secret,
)
from neobot_adapter.official.settings import OfficialSettings

_CREATE_URL = "https://q.qq.com/lite/create_bind_task"
_POLL_URL = "https://q.qq.com/lite/poll_bind_result"
_NONCE = b"abcdefghijkl"
_COMPLETED_SECRET = "bound-secret"


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ── 替身 ────────────────────────────────────────────────────────────


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
    """按 URL 脚本化返回响应，并记录每次 POST。"""

    def __init__(self, *, status: int = 200, payload: Any = None) -> None:
        self.requests: list[tuple[str, dict[str, Any], Any]] = []
        self.queues: dict[str, list[Any]] = {}
        self.default = (status, payload if payload is not None else {})

    def script(self, url: str, *items: Any) -> None:
        self.queues.setdefault(url, []).extend(items)

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: Any = None,
    ) -> FakeResponse:
        self.requests.append((url, json, headers))
        queue = self.queues.get(url)
        item = queue.pop(0) if queue else self.default
        if callable(item):
            item = item(json)
        status, payload = item
        return FakeResponse(status, payload)


class FakeLogger:
    def __init__(self) -> None:
        self.debugs: list[tuple[str, dict[str, Any]]] = []
        self.infos: list[tuple[str, dict[str, Any]]] = []
        self.warnings: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, dict[str, Any]]] = []

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


def _settings(work_dir: Path, **overrides: Any) -> OfficialSettings:
    values: dict[str, Any] = {
        "app_id": "123456",
        "client_secret": "client-secret",
        "data_dir": work_dir,
    }
    values.update(overrides)
    return OfficialSettings(**values)


def _encrypt(secret: str, key: bytes) -> str:
    ciphertext = AESGCM(key).encrypt(_NONCE, secret.encode("utf-8"), None)
    return base64.b64encode(_NONCE + ciphertext).decode("ascii")


def _bind_flow_http(
    *,
    task_ids: list[str],
    poll_statuses: list[int],
) -> tuple[FakeHttp, dict[str, str]]:
    """create/poll 脚本：成功状态自动用 create 时的 key 加密返回。"""
    http = FakeHttp()
    captured: dict[str, str] = {}

    def create(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        captured["key"] = payload["key"]
        task_id = task_ids.pop(0) if task_ids else "task-x"
        return 200, {"retcode": 0, "data": {"task_id": task_id}}

    def complete(_payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        key = base64.b64decode(captured["key"])
        return 200, {
            "retcode": 0,
            "data": {
                "status": 2,
                "bot_appid": "888",
                "bot_encrypt_secret": _encrypt(_COMPLETED_SECRET, key),
            },
        }

    # 二维码过期时同一把 key 会再 create 一次，脚本预置两份。
    http.script(_CREATE_URL, create, create)
    for status in poll_statuses:
        if status == 2:
            http.script(_POLL_URL, complete)
        else:
            http.script(_POLL_URL, (200, {"retcode": 0, "data": {"status": status}}))
    return http, captured


# ── OfficialSettings ────────────────────────────────────────────────


def test_settings_from_adapter_settings_reads_qq_fields(workdir: Path) -> None:
    adapter_settings = SimpleNamespace(
        qq_appid="app",
        qq_client_secret="secret",
        qq_base_url="https://api.example.com",
        qq_token_url="https://api.example.com/token",
        qq_portal_host="portal.example.com",
        data_dir=str(workdir),
    )

    settings = OfficialSettings.from_adapter_settings(adapter_settings)

    assert settings.app_id == "app"
    assert settings.client_secret == "secret"
    assert settings.base_url == "https://api.example.com"
    assert settings.token_url == "https://api.example.com/token"
    assert settings.portal_host == "portal.example.com"
    assert settings.data_dir == workdir
    assert settings.bind_timeout_seconds == 600.0


def test_settings_from_adapter_settings_falls_back_to_defaults() -> None:
    settings = OfficialSettings.from_adapter_settings(SimpleNamespace())

    assert settings.app_id == ""
    assert settings.client_secret == ""
    assert settings.base_url == "https://api.bot.qq.com"
    assert settings.token_url == "https://api.bot.qq.com/app/getAppAccessToken"
    assert settings.portal_host == "q.qq.com"
    assert settings.data_dir == Path("data")


def test_settings_portal_host_normalizes_scheme_and_explicit_data_dir(
    workdir: Path,
) -> None:
    settings = OfficialSettings.from_adapter_settings(
        SimpleNamespace(qq_portal_host="https://q.qq.com/", data_dir="ignored"),
        data_dir=workdir,
    )

    assert settings.portal_host == "q.qq.com"
    assert settings.data_dir == workdir


# ── CredentialStore ─────────────────────────────────────────────────


def test_credential_store_roundtrip_permissions_and_atomic_write(
    workdir: Path,
) -> None:
    store = CredentialStore(workdir)
    assert store.load() is None

    store.save("123456", "secret-value")

    assert store.load() == Credentials(app_id="123456", client_secret="secret-value")
    path = workdir / "qqbot" / "credentials.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "app_id": "123456",
        "client_secret": "secret-value",
    }
    # 原子写完成后目录里只剩正式文件，没有临时文件残留。
    assert sorted(item.name for item in path.parent.iterdir()) == ["credentials.json"]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    store.delete()
    assert store.load() is None
    store.delete()


def test_credential_store_rejects_empty_credentials(workdir: Path) -> None:
    store = CredentialStore(workdir)
    with pytest.raises(OfficialAuthError):
        store.save("", "secret")
    with pytest.raises(OfficialAuthError):
        store.save("123456", "  ")


def test_credential_store_returns_none_for_corrupt_file(workdir: Path) -> None:
    path = workdir / "qqbot" / "credentials.json"
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")
    assert CredentialStore(workdir).load() is None


# ── TokenProvider ───────────────────────────────────────────────────


async def test_token_provider_caches_until_80_percent(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(workdir)
    http = FakeHttp()
    http.script(settings.token_url, (200, {"access_token": "tok-1", "expires_in": 100}))
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(auth, "time", SimpleNamespace(monotonic=lambda: clock.now))
    provider = TokenProvider(settings, http)

    assert await provider.get_token() == "tok-1"
    clock.now = 1000.0 + 79.0
    assert await provider.get_token() == "tok-1"
    assert len(http.requests) == 1

    http.script(settings.token_url, (200, {"access_token": "tok-2", "expires_in": 100}))
    clock.now = 1000.0 + 81.0
    assert await provider.get_token() == "tok-2"
    assert len(http.requests) == 2
    assert http.requests[0][1] == {"appId": "123456", "clientSecret": "client-secret"}


async def test_token_provider_force_and_invalidate_refetch(workdir: Path) -> None:
    settings = _settings(workdir)
    http = FakeHttp(status=200, payload={"access_token": "tok", "expires_in": 7200})
    provider = TokenProvider(settings, http)

    assert await provider.get_token() == "tok"
    assert await provider.get_token(force=True) == "tok"
    assert len(http.requests) == 2

    provider.invalidate()
    assert await provider.get_token() == "tok"
    assert len(http.requests) == 3


class _BlockingHttp:
    def __init__(self) -> None:
        self.calls = 0
        self.release = asyncio.Event()

    def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: Any = None,
    ) -> "_BlockingResponse":
        self.calls += 1
        return _BlockingResponse(self)


class _BlockingResponse:
    status = 200

    def __init__(self, http: _BlockingHttp) -> None:
        self._http = http

    async def json(self, content_type: str | None = None) -> Any:
        await self._http.release.wait()
        return {"access_token": "tok", "expires_in": 7200}

    async def __aenter__(self) -> "_BlockingResponse":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


async def test_token_provider_single_flight(workdir: Path) -> None:
    http = _BlockingHttp()
    provider = TokenProvider(_settings(workdir), http)

    tasks = [asyncio.create_task(provider.get_token()) for _ in range(3)]
    for _ in range(100):
        if http.calls:
            break
        await asyncio.sleep(0.01)
    http.release.set()

    assert await asyncio.gather(*tasks) == ["tok", "tok", "tok"]
    assert http.calls == 1


async def test_token_provider_requires_credentials(workdir: Path) -> None:
    provider = TokenProvider(
        _settings(workdir, app_id="", client_secret=""),
        FakeHttp(),
    )
    with pytest.raises(OfficialAuthError, match="AppID"):
        await provider.get_token()


async def test_token_provider_surfaces_http_failure(workdir: Path) -> None:
    http = FakeHttp(status=401, payload={"message": "invalid appid"})
    provider = TokenProvider(_settings(workdir), http)
    with pytest.raises(OfficialAuthError, match="401"):
        await provider.get_token()


async def test_token_provider_requires_access_token(workdir: Path) -> None:
    http = FakeHttp(status=200, payload={"message": "no token"})
    provider = TokenProvider(_settings(workdir), http)
    with pytest.raises(OfficialAuthError, match="access token"):
        await provider.get_token()


# ── AES-GCM 解密 ────────────────────────────────────────────────────


def test_decrypt_secret_with_known_vector() -> None:
    key = bytes(range(32))
    encrypted = _encrypt("secret-value", key)

    assert decrypt_secret(encrypted, base64.b64encode(key).decode("ascii")) == "secret-value"


def test_decrypt_secret_rejects_tampered_or_malformed_payloads() -> None:
    key = bytes(range(32))
    key_b64 = base64.b64encode(key).decode("ascii")
    tampered = bytearray(base64.b64decode(_encrypt("secret-value", key)))
    tampered[-1] ^= 0xFF

    with pytest.raises(OfficialAuthError):
        decrypt_secret(base64.b64encode(bytes(tampered)).decode("ascii"), key_b64)
    with pytest.raises(OfficialAuthError):
        decrypt_secret("not-base64", key_b64)
    with pytest.raises(OfficialAuthError):
        decrypt_secret(_encrypt("secret-value", key), base64.b64encode(b"short").decode("ascii"))


# ── QrBindFlow ──────────────────────────────────────────────────────


async def test_qr_bind_flow_completes_and_persists_credentials(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_POLL_INTERVAL_SECONDS", 0)
    printed: list[str] = []
    monkeypatch.setattr(auth, "_print_ascii_qr", printed.append)
    http, _captured = _bind_flow_http(task_ids=["task-1"], poll_statuses=[1, 2])
    logger = FakeLogger()
    states: list[BindState] = []

    async def on_update(state: BindState) -> None:
        states.append(state)

    flow = QrBindFlow(_settings(workdir), logger, http)
    state = await flow.start(on_update)

    assert state.phase == "success"
    assert flow.state is state
    assert [item.phase for item in states] == ["pending", "success"]
    assert len(printed) == 1
    pending = states[0]
    assert pending.url == "https://q.qq.com/qqbot/openclaw/connect.html?task_id=task-1&_wv=2&source=neobot"
    assert "<svg" in pending.svg
    assert pending.expires_at > 0
    assert CredentialStore(workdir).load() == Credentials(app_id="888", client_secret=_COMPLETED_SECRET)
    assert any("扫码绑定" in message for message, _kw in logger.infos)


async def test_qr_bind_flow_rebuilds_expired_qr_once_and_prints_ascii_once(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "_POLL_INTERVAL_SECONDS", 0)
    printed: list[str] = []
    monkeypatch.setattr(auth, "_print_ascii_qr", printed.append)
    http, _captured = _bind_flow_http(
        task_ids=["task-1", "task-2"],
        poll_statuses=[3, 2],
    )
    states: list[BindState] = []

    flow = QrBindFlow(_settings(workdir), FakeLogger(), http)
    state = await flow.start(states.append)

    assert state.phase == "success"
    assert len(printed) == 1
    assert [item.url for item in states if item.phase == "pending"] == [
        "https://q.qq.com/qqbot/openclaw/connect.html?task_id=task-1&_wv=2&source=neobot",
        "https://q.qq.com/qqbot/openclaw/connect.html?task_id=task-2&_wv=2&source=neobot",
    ]
    # 过期重建沿用同一个 AES key，只用 create 换了 task_id。
    create_requests = [payload for url, payload, _headers in http.requests if url == _CREATE_URL]
    assert len(create_requests) == 2
    assert create_requests[0]["key"] == create_requests[1]["key"]


async def test_qr_bind_flow_times_out(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_POLL_INTERVAL_SECONDS", 0.005)
    monkeypatch.setattr(auth, "_print_ascii_qr", lambda url: None)
    http = FakeHttp(status=200, payload={"retcode": 0, "data": {"status": 1}})
    http.script(_CREATE_URL, (200, {"retcode": 0, "data": {"task_id": "task-1"}}))
    states: list[BindState] = []

    flow = QrBindFlow(_settings(workdir, bind_timeout_seconds=0.05), FakeLogger(), http)
    state = await flow.start(states.append)

    assert state.phase == "expired"
    assert "超时" in state.error
    assert [item.phase for item in states] == ["pending", "expired"]


async def test_qr_bind_flow_reports_create_failure(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(auth, "_print_ascii_qr", printed.append)
    http = FakeHttp(status=500, payload={"message": "portal down"})
    logger = FakeLogger()

    flow = QrBindFlow(_settings(workdir), logger, http)
    state = await flow.start()

    assert state.phase == "error"
    assert "HTTP 500" in state.error
    assert printed == []
    assert logger.errors
    assert CredentialStore(workdir).load() is None
