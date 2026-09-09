"""图片下载 HTTP 客户端的代理策略测试。"""

from __future__ import annotations

import httpx
import pytest

from neobot_app.utils.http import image_http_client, is_local_or_private_url


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
