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
import os
import re
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


#: 带方括号的 IPv6 字面量条目，例如 "[::1]"、"[fe80::1]"
_BRACKETED_IPV6_ENTRY = re.compile(r"^\[([0-9A-Fa-f:.]+)\]$")

#: no_proxy 环境变量可能的大小写形态（Windows 上两者都可能出现）
_NO_PROXY_KEYS = ("no_proxy", "NO_PROXY")


def normalize_no_proxy_entry(entry: str) -> str:
    """把 "[::1]" 这类**带方括号**的 IPv6 字面量还原成不带方括号的形态。

    背景（真机启动即崩溃）：httpx 只把**不带方括号**的 IPv6 识别为 IPv6
    （is_ipv6_hostname("::1") 为真，生成合法的 all://[::1]）；
    "[::1]" 会被当成域名通配条目，生成非法的 all://*[::1]，
    构造客户端时抛 httpx.InvalidURL: Invalid port: ':1]'。

    而 NO_PROXY=localhost,127.0.0.1,::1,[::1] 是 Clash 类代理工具写进环境变量的
    常见取值，于是 NeoBot 会在装配阶段（第一个 trust_env=True 的客户端）整体启动失败。
    去掉方括号后 httpx 会生成正确的 all://[::1]，「该地址不走代理」的语义完全不变。
    """
    token = str(entry or "").strip()
    match = _BRACKETED_IPV6_ENTRY.match(token)
    if not match:
        return token
    inner = match.group(1)
    try:
        ipaddress.IPv6Address(inner)
    except ValueError:
        return token  # 不是合法 IPv6（例如 "[example]"）：不是本函数负责的形态
    return inner


def sanitize_no_proxy_environment() -> list[str]:
    """就地规范化进程环境里的 no_proxy，返回被改写的**原始**条目。

    这是启动期加固，不读也不改任何配置文件：只把 httpx 无法表达的
    「带方括号 IPv6」条目还原成它能正确处理的形态，并顺带去重。
    httpx 之后的代理判定与之前完全一致，只是不再抛异常。
    """
    changed: list[str] = []
    for key in _NO_PROXY_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        tokens: list[str] = []
        seen: set[str] = set()
        for item in raw.replace(" ", "").split(","):
            if not item:
                continue
            normalized = normalize_no_proxy_entry(item)
            if normalized != item and item not in changed:
                changed.append(item)
            if normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
        cleaned = ",".join(tokens)
        if cleaned != raw:
            os.environ[key] = cleaned
    return changed


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
