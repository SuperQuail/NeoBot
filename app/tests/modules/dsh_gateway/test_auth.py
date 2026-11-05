"""认证：Bearer token 常量时间比较、IP 白名单 / CIDR、反代头与回环判断。"""

from __future__ import annotations

import pytest

from neobot_app.dsh_gateway.auth import (
    IpAllowList,
    extract_bearer_token,
    ip_allowed,
    is_loopback_host,
    parse_allow_ips,
    resolve_client_ip,
    token_matches,
)


class _FakeRequest:
    def __init__(self, remote: str | None = "127.0.0.1", headers: dict[str, str] | None = None) -> None:
        self.remote = remote
        self.headers = headers or {}


@pytest.mark.parametrize("header", ["Bearer s3cret", "bearer s3cret", "BEARER   s3cret  "])
def test_token_matches_accepts_correct_token(header):
    assert extract_bearer_token(header) == "s3cret"
    assert token_matches(header, "s3cret") is True


@pytest.mark.parametrize(
    "header",
    [None, "", "s3cret", "Bearer", "Bearer ", "Basic s3cret", "Bearer wrong", "Bearer s3cret extra"],
)
def test_token_matches_rejects_bad_headers(header):
    assert token_matches(header, "s3cret") is False


def test_token_matches_rejects_when_expected_token_empty():
    assert token_matches("Bearer whatever", "") is False
    assert token_matches("Bearer ", "") is False


@pytest.mark.parametrize(
    ("remote", "allowed"),
    [
        ("192.168.1.10", True),
        ("192.168.1.10", True),
        ("10.0.0.5", False),
        (None, False),
        ("not-an-ip", False),
    ],
)
def test_ip_allow_list_single_ip(remote, allowed):
    allow_list = IpAllowList(["192.168.1.10"])

    assert allow_list.allows(remote) is allowed
    assert bool(allow_list) is True


@pytest.mark.parametrize(
    ("remote", "allowed"),
    [
        ("10.1.2.3", True),
        ("10.255.0.1", True),
        ("11.0.0.1", False),
        ("192.168.1.10", False),
    ],
)
def test_ip_allow_list_cidr(remote, allowed):
    assert IpAllowList(["10.0.0.0/8"]).allows(remote) is allowed


def test_ip_allow_list_supports_multiple_entries_and_ipv6():
    allow_list = IpAllowList(["192.168.1.10", "10.0.0.0/8", "::1", "fd00::/8"])

    assert allow_list.allows("192.168.1.10") is True
    assert allow_list.allows("10.9.9.9") is True
    assert allow_list.allows("::1") is True
    assert allow_list.allows("fd12::1") is True
    assert allow_list.allows("172.16.0.1") is False


def test_empty_allow_list_allows_everyone():
    allow_list = IpAllowList([])

    assert allow_list.allows("203.0.113.9") is True
    assert allow_list.allows(None) is True
    assert bool(allow_list) is False


def test_invalid_allow_list_entry_raises_value_error():
    with pytest.raises(ValueError, match="非法"):
        IpAllowList(["10.0.0.0/8", "not-a-network"])


def test_parse_allow_ips_skips_blank_entries():
    networks = parse_allow_ips([" ", "", "127.0.0.1"])

    assert len(networks) == 1
    assert ip_allowed("127.0.0.1", networks) is True


def test_resolve_client_ip_ignores_forwarded_for_by_default():
    request = _FakeRequest(remote="192.168.1.20", headers={"X-Forwarded-For": "203.0.113.9"})

    assert resolve_client_ip(request) == "192.168.1.20"


def test_resolve_client_ip_uses_forwarded_for_when_trusted():
    request = _FakeRequest(
        remote="10.0.0.1",
        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )

    assert resolve_client_ip(request, trust_forwarded_for=True) == "203.0.113.9"
    assert resolve_client_ip(request) == "10.0.0.1"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.1.2.3", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", False),
        ("", False),
        ("192.168.1.10", False),
        ("example.com", False),
    ],
)
def test_is_loopback_host(host, expected):
    assert is_loopback_host(host) is expected
