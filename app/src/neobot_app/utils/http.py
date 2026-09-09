"""HTTP 客户端辅助 — 图片下载等场景的代理策略。

图片 URL 常指向 Bot 自己的文件服务器（`127.0.0.1` / 内网 IP）。httpx 默认
`trust_env=True`，会读取环境变量与 Windows 注册表中的系统代理；开启系统代理
（如 Clash、公司代理）的机器上，连 `127.0.0.1` 的请求也会被转发出去并失败
（典型表现是 502 Bad Gateway），导致"自己上传的图片反而解析不了"。

因此图片下载统一走 :func:`image_http_client`：目标为本机/私有地址时禁用代理信任，
公网地址保持默认行为（该走代理仍走代理）。
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

import httpx

# 常见本机/内网主机名
_LOCAL_HOST_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".localdomain", ".internal", ".lan", ".home")


def is_local_or_private_url(url: Any) -> bool:
    """判断 URL 是否指向本机或私有网段（这类请求不应经过系统代理）。"""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.strip("[]").rstrip(".").lower()
    if host in _LOCAL_HOST_NAMES or host.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


def image_http_client(
    *,
    timeout: Any = 30.0,
    follow_redirects: bool = False,
    url: Any = None,
) -> httpx.AsyncClient:
    """构造图片下载用 httpx 客户端。

    `url` 指向本机/私有地址时使用 `trust_env=False`，绕过系统代理；
    公网地址保持 httpx 默认（尊重环境/系统代理配置）。
    """
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        trust_env=not is_local_or_private_url(url),
    )
