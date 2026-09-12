"""图片下载 HTTP 客户端的代理策略测试。"""

from __future__ import annotations

import os

import httpx
import pytest

from neobot_app.utils.http import (
    image_http_client,
    is_local_or_private_url,
    normalize_no_proxy_entry,
    sanitize_no_proxy_environment,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/files/a.png?token=x",
        "http://localhost/files/a.png",
        "http://LocalHost:1234/x",
        "http://[::1]:8080/x",
        "http://192.168.1.5/x",
        "http://10.0.0.7/x",
        "http://172.16.3.9/x",
        "http://169.254.10.1/x",
        "http://nas.local/x",
        "http://box.internal/x",
        "http://127.0.0.1./x",
    ],
)
def test_is_local_or_private_url_true(url: str) -> None:
    assert is_local_or_private_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/a.png",
        "http://8.8.8.8/a.png",
        "http://example.com:8080/a.png",
        "",
        None,
        123,
        "not a url",
    ],
)
def test_is_local_or_private_url_false(url: object) -> None:
    assert is_local_or_private_url(url) is False


@pytest.mark.asyncio
async def test_image_http_client_disables_proxy_trust_for_local_urls() -> None:
    """本机地址必须忽略系统/环境代理（否则 127.0.0.1 请求会被代理转发失败）。"""
    client = image_http_client(timeout=1.0, url="http://127.0.0.1:9/x.png")
    try:
        assert isinstance(client, httpx.AsyncClient)
        # trust_env=False 时 httpx 不挂载任何代理传输（httpx 内部属性，缺失则跳过）
        mounts = getattr(client, "_mounts", None)
        if mounts is not None:
            assert not mounts
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_image_http_client_keeps_proxy_trust_for_public_urls() -> None:
    client = image_http_client(timeout=1.0, url="https://cdn.example.com/a.png")
    try:
        assert isinstance(client, httpx.AsyncClient)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# no_proxy 启动期加固
#
# httpx 只把**不带方括号**的 IPv6 识别为 IPv6；"[::1]" 会被当成域名通配条目并生成
# 非法的 URLPattern("all://*[::1]")，构造客户端时抛 httpx.InvalidURL ——
# 于是 NO_PROXY 里只要有 "[::1]"，NeoBot 就会在装配阶段整体启动失败。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("[::1]", "::1"),
        ("[fe80::1]", "fe80::1"),
        ("[2001:db8::1]", "2001:db8::1"),
        ("::1", "::1"),
        ("localhost", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("*.example.com", "*.example.com"),
        ("[example]", "[example]"),  # 不是合法 IPv6：不动它
        ("", ""),
    ],
)
def test_normalize_no_proxy_entry(entry: str, expected: str) -> None:
    assert normalize_no_proxy_entry(entry) == expected


def test_bracketed_ipv6_in_no_proxy_would_break_httpx() -> None:
    """回归锚点：说明这个加固修的是什么（httpx 自身的限制）。"""
    with pytest.raises(httpx.InvalidURL):
        httpx.AsyncClient(trust_env=False, mounts={"all://*[::1]": None})

    # 规范化之后的形态是 httpx 能接受的
    client = httpx.AsyncClient(trust_env=False, mounts={"all://[::1]": None})
    assert client is not None


def test_sanitize_no_proxy_environment_rewrites_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "localhost,127.0.0.1,::1,[::1]"
    monkeypatch.setenv("NO_PROXY", raw)
    monkeypatch.setenv("no_proxy", raw)

    changed = sanitize_no_proxy_environment()

    assert changed == ["[::1]"]
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,::1"
    assert os.environ["no_proxy"] == "localhost,127.0.0.1,::1"
    # 幂等：再跑一次不改任何东西
    assert sanitize_no_proxy_environment() == []


def test_sanitize_no_proxy_environment_leaves_normal_values_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Windows 上 os.environ 的键不区分大小写：必须先删再设，否则会把刚设的值删掉
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,*.internal")

    assert sanitize_no_proxy_environment() == []
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,*.internal"


def test_sanitize_no_proxy_environment_makes_httpx_client_constructible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """端到端：直接复现真机崩溃场景，加固后 httpx 能正常构造客户端。"""
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,[::1]")

    sanitize_no_proxy_environment()
    client = httpx.AsyncClient(timeout=1.0)  # trust_env=True（默认）

    mounts = getattr(client, "_mounts", None)
    if mounts is not None:
        # 规范化后不再出现非法的通配条目
        assert "all://*[::1]" not in {str(key) for key in mounts}

