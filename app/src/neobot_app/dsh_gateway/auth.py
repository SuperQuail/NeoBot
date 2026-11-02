"""网关认证：Bearer token 常量时间比较、来源 IP 白名单与反代地址解析。

v1 默认不信任 ``X-Forwarded-For``（只有显式传 ``trust_forwarded_for=True`` 才读），
因为网关默认直连、没有可信反代时该头可被客户端随意伪造。
"""

from __future__ import annotations

import hmac
import ipaddress
from typing import Any, Iterable

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_BEARER_SCHEME = "bearer"


def extract_bearer_token(header_value: str | None) -> str | None:
    """从 ``Authorization`` 头里取出 Bearer token；格式不符返回 None。"""
    if not isinstance(header_value, str):
        return None
    scheme, separator, credentials = header_value.partition(" ")
    if not separator or scheme.strip().lower() != _BEARER_SCHEME:
        return None
    token = credentials.strip()
    return token or None


def token_matches(header_value: str | None, expected_token: str) -> bool:
    """常量时间比较请求头与配置 token；未配置 token 时恒为 False。"""
    expected = str(expected_token or "")
    if not expected:
        return False
    token = extract_bearer_token(header_value)
    if token is None:
        return False
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def parse_allow_ips(entries: Iterable[str] | None) -> tuple[IpNetwork, ...]:
    """把配置项解析成网络列表；单个 IP 按 /32 或 /128 处理，非法项抛 ValueError。"""
    networks: list[IpNetwork] = []
    for entry in entries or ():
        text = str(entry or "").strip()
        if not text:
            continue
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError as exc:
            raise ValueError(f"非法的 IP / CIDR 白名单项: {text!r}") from exc
    return tuple(networks)


def ip_allowed(remote_ip: str | None, networks: tuple[IpNetwork, ...]) -> bool:
    """网络列表为空表示不限制来源；地址解析失败按不允许处理。"""
    if not networks:
        return True
    if not remote_ip:
        return False
    try:
        address = ipaddress.ip_address(str(remote_ip).strip())
    except ValueError:
        return False
    return any(address in network for network in networks)


class IpAllowList:
    """IP / CIDR 白名单；空列表表示不限制来源（只靠 token 认证）。"""

    def __init__(self, entries: Iterable[str] | None = ()) -> None:
        self._networks = parse_allow_ips(entries)

    @property
    def networks(self) -> tuple[IpNetwork, ...]:
        return self._networks

    def allows(self, remote_ip: str | None) -> bool:
        return ip_allowed(remote_ip, self._networks)

    def __bool__(self) -> bool:
        return bool(self._networks)


def resolve_client_ip(request: Any, *, trust_forwarded_for: bool = False) -> str | None:
    """取客户端 IP。

    只有部署在可信反向代理后面时才应把 ``trust_forwarded_for`` 打开；否则
    ``X-Forwarded-For`` 可被伪造，直接看 TCP 连接来源（``request.remote``）。
    """
    if trust_forwarded_for:
        headers = getattr(request, "headers", None)
        forwarded = headers.get("X-Forwarded-For") if headers is not None else None
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
    return getattr(request, "remote", None)


def is_loopback_host(host: str | None) -> bool:
    """监听地址是否只在本机回环（空 host / 通配地址 / 普通主机名都按非回环处理）。"""
    text = str(host or "").strip().lower()
    if not text:
        return False
    if text in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


__all__ = [
    "IpAllowList",
    "IpNetwork",
    "extract_bearer_token",
    "ip_allowed",
    "is_loopback_host",
    "parse_allow_ips",
    "resolve_client_ip",
    "token_matches",
]
