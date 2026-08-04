"""SSRF 防护工具与 download_file 下载防护测试。"""

from __future__ import annotations

import json

import httpx
import pytest

from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill
from neobot_app.utils import ssrf


def _public_resolver(host: str, port: int, type: int = 0) -> list[tuple]:
    return [
        (2, 1, 6, "", ("8.8.8.8", 0)),
        (10, 1, 6, "", ("2001:4860:4860::8888", 0, 0, 0)),
    ]


def test_validate_public_url_rejects_private_ip_literals():
    for host in (
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ):
        assert ssrf.validate_public_url(f"http://{host}/x") is False, host
        assert ssrf.validate_public_url(f"https://{host}:443/x") is False, host


def test_validate_public_url_rejects_encoded_ips():
    assert ssrf.validate_public_url("http://2130706433/") is False
    assert ssrf.validate_public_url("http://0x7f000001/") is False
    assert ssrf.validate_public_url("http://0177.0.0.1/") is False
    assert ssrf.validate_public_url("http://127.1/") is False


def test_validate_public_url_rejects_bad_scheme_and_missing_host():
    assert ssrf.validate_public_url("ftp://8.8.8.8/file") is False
    assert ssrf.validate_public_url("file:///etc/passwd") is False
    assert ssrf.validate_public_url("javascript:alert(1)") is False
    assert ssrf.validate_public_url("http:///path") is False
    assert ssrf.validate_public_url("not-a-url") is False


def test_validate_public_url_accepts_public_ips():
    assert ssrf.validate_public_url("http://8.8.8.8/") is True
    assert ssrf.validate_public_url("https://1.1.1.1:443/x") is True
    assert ssrf.validate_public_url("http://[2606:4700:4700::1111]/") is True


def test_validate_public_url_resolves_public_domain(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _public_resolver)
    assert ssrf.validate_public_url("http://example.com/") is True


def test_validate_public_url_rejects_internal_domain(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket,
        "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", ("192.168.1.1", 0))],
    )
    assert ssrf.validate_public_url("http://internal.example.com/") is False


def test_validate_public_url_rejects_localhost_domain(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket,
        "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    assert ssrf.validate_public_url("http://localhost/") is False


def test_validate_public_url_rejects_domain_with_any_private_addr(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (2, 1, 6, "", ("8.8.8.8", 0)),
            (2, 1, 6, "", ("10.0.0.1", 0)),
        ],
    )
    assert ssrf.validate_public_url("http://mixed.example.com/") is False


def test_validate_public_url_rejects_unresolvable_domain(monkeypatch):
    def raise_nxdomain(host: str, port: int, type: int = 0) -> list[tuple]:
        raise OSError("NXDOMAIN")

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", raise_nxdomain)
    assert ssrf.validate_public_url("http://no-such-domain.invalid/") is False


def test_private_endpoint_allowlist():
    ssrf.allow_private_endpoint("127.0.0.1", 9981)
    try:
        assert ssrf.validate_public_url("http://127.0.0.1:9981/console") is True
        assert ssrf.validate_public_url("http://127.0.0.1:9982/") is False
        assert ssrf.validate_public_url("http://10.0.0.5:9981/") is False
    finally:
        ssrf.clear_private_endpoints()


async def test_validate_public_url_async_rejects_private_ip():
    assert await ssrf.validate_public_url_async("http://192.168.1.1/x") is False


class _FakeResponse:
    def __init__(self, status_code: int = 200, headers: dict | None = None, chunks: list[bytes] | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.url = "http://fake.invalid/"

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", self.url),
                response=httpx.Response(self.status_code, request=httpx.Request("GET", self.url)),
            )

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        return self._handler(url)


@pytest.fixture
def fake_public_dns(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _public_resolver)


async def _run_download(skill: SandboxManagerSkill, **args) -> dict:
    return json.loads(await skill.execute("download_file", args))


async def test_download_file_rejects_redirect_to_private(fake_public_dns, monkeypatch, tmp_path):
    seen: list[str] = []

    def handler(url: str) -> _FakeResponse:
        seen.append(url)
        return _FakeResponse(status_code=302, headers={"location": "http://10.0.0.1/evil"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    skill = SandboxManagerSkill(sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"))
    result = await _run_download(skill, url="http://example.com/f.bin", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is False
    assert "重定向目标不允许下载" in result["error"]
    assert seen == ["http://example.com/f.bin"]


async def test_download_file_rejects_initial_private_url(fake_public_dns, monkeypatch, tmp_path):
    def handler(url: str) -> _FakeResponse:
        raise AssertionError("不应发起请求")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    skill = SandboxManagerSkill(sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"))
    result = await _run_download(skill, url="http://169.254.169.254/latest/meta-data/", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is False
    assert "非公网" in result["error"]


async def test_download_file_rejects_oversized_by_content_length(fake_public_dns, monkeypatch, tmp_path):
    def handler(url: str) -> _FakeResponse:
        return _FakeResponse(status_code=200, headers={"content-length": "200000000"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    skill = SandboxManagerSkill(sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"))
    result = await _run_download(skill, url="http://example.com/big.bin", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is False
    assert "超过上限" in result["error"]


async def test_download_file_aborts_when_stream_exceeds_limit(fake_public_dns, monkeypatch, tmp_path):
    big_chunk = b"x" * (60 * 1024 * 1024)

    def handler(url: str) -> _FakeResponse:
        return _FakeResponse(status_code=200, headers={}, chunks=[big_chunk, big_chunk])

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    skill = SandboxManagerSkill(sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"))
    result = await _run_download(skill, url="http://example.com/big.bin", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is False
    assert "已中止" in result["error"]


async def test_download_file_limits_redirect_chain(fake_public_dns, monkeypatch, tmp_path):
    seen: list[str] = []

    def handler(url: str) -> _FakeResponse:
        seen.append(url)
        return _FakeResponse(status_code=302, headers={"location": "http://8.8.8.8/again"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    skill = SandboxManagerSkill(sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"))
    result = await _run_download(skill, url="http://example.com/a", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is False
    assert "重定向次数超过限制" in result["error"]
    assert len(seen) == 4


async def test_download_file_streams_and_saves(fake_public_dns, monkeypatch, tmp_path):
    def handler(url: str) -> _FakeResponse:
        return _FakeResponse(
            status_code=200,
            headers={"content-type": "application/octet-stream"},
            chunks=[b"hello", b" ", b"world"],
        )

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(handler))
    sandbox = SandboxService(sandbox_root=tmp_path / "sandbox")
    skill = SandboxManagerSkill(sandbox_service=sandbox)
    result = await _run_download(skill, url="http://example.com/f.bin", save_name="f.bin", chat_flow_id="t")
    assert result["ok"] is True
    assert result["size"] == 11
    saved = tmp_path / "sandbox" / "temp" / "t" / "f.bin"
    assert saved.read_bytes() == b"hello world"
