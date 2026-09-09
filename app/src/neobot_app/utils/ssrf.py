"""SSRF 防护工具 — 仅允许请求公网地址（http/https）。

提供 URL 校验（IP 字面量 / DNS 解析均需为公网地址），以及私有端点白名单
（用于允许 Bot 访问自身开启的非管理员控制台）。
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

_ALLOWED_PRIVATE_ENDPOINTS: set[tuple[str, int]] = set()

# 十进制 / 十六进制 / 八进制编码的 IP 形式（如 2130706433、0x7f000001、0177.0.0.1）
_ENCODED_IP_RE = re.compile(
    r"^(?:\d+|0[xX][0-9a-fA-F]+|0[0-7]+)(?:\.(?:\d+|0[xX][0-9a-fA-F]+|0[0-7]+))*$"
)


def allow_private_endpoint(host: str, port: int) -> None:
    """注册允许访问的私有端点（host:port，如 Bot 自身的非管理员控制台）。"""
    _ALLOWED_PRIVATE_ENDPOINTS.add((host.lower(), int(port)))


def clear_private_endpoints() -> None:
    """清空私有端点白名单。"""
    _ALLOWED_PRIVATE_ENDPOINTS.clear()


def _is_private_endpoint_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    return (host, port) in _ALLOWED_PRIVATE_ENDPOINTS


def _looks_like_encoded_ip(hostname: str) -> bool:
    if not hostname:
        return False
    return _ENCODED_IP_RE.fullmatch(hostname) is not None


def _is_public_ip(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr).is_global
    except ValueError:
        return False


def validate_public_url(url: str) -> bool:
    """校验 URL 是否指向公网地址。

    仅允许 http/https；IP 字面量（含十进制/十六进制编码形式）必须为公网地址；
    域名解析出的所有地址必须为公网地址。DNS rebinding 无法在此完全杜绝。
    """
    if _is_private_endpoint_allowed(url):
        return True
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc.count(":") > 1 and not parsed.netloc.startswith("["):
        # 未加方括号的 IPv6 字面量（如 http://fc00::1/）：URL 语法非法，直接拒绝，
        # 否则 urlparse 会把 "fc00" 当成主机名去做 DNS 解析，白等数秒
        return False
    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None:
        return ip.is_global

    if ":" in hostname:
        # 含冒号却解析不出 IP 的主机名（例如未加方括号的 IPv6 字面量）语法非法：
        # 直接判为非公网，避免走 DNS 解析白等几秒
        return False

    if _looks_like_encoded_ip(hostname):
        return False

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    return all(_is_public_ip(info[4][0]) for info in infos)


async def validate_public_url_async(url: str) -> bool:
    """异步版本：DNS 解析在 to_thread 中执行，避免阻塞事件循环。"""
    return await asyncio.to_thread(validate_public_url, url)
