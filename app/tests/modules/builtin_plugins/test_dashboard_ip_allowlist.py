"""dashboard 来源 IP 白名单（allowed_ips）。

守住四件事：
1. 留空 = 不限制（默认行为，老部署升级后表现不变）；
2. 回环地址**始终放行** —— 白名单配错时面板仍能在本机救回来；
3. 条目解析失败**不等于放行**：它永不匹配，结果是除本机外全拒（fail-closed），
   并且**不能**让配置校验整体失败（那会让字段回落成空列表 = 放开所有限制）；
4. 白名单保存后立即生效（请求期判定），不需要重启进程。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiohttp import web

from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.hot_reload import DashboardConfigConsumer
from neobot_app.builtin_plugins.dashboard.security import (
    IpAllowList,
    build_ip_allow_list,
    is_loopback,
)
from neobot_app.builtin_plugins.dashboard.server import DashboardServer


class _NullLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None: ...
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...


class _RecordingLogger(_NullLogger):
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.warnings.append(str(message))


# ---------------------------------------------------------------------------
# 编译与匹配（纯逻辑，不起 HTTP 服务）
# ---------------------------------------------------------------------------


def test_empty_allow_list_does_not_restrict() -> None:
    """没配白名单 = 不限制，任何来源都放行。"""
    for empty in (None, [], [""], ["   "]):
        allow = build_ip_allow_list(empty)
        assert allow.enabled is False
        assert allow.allows("203.0.113.9") is True
        assert allow.allows("not-an-ip") is True


def test_bare_ip_matches_only_that_host() -> None:
    allow = build_ip_allow_list(["192.168.1.5"])

    assert allow.enabled is True
    assert allow.allows("192.168.1.5") is True
    assert allow.allows("192.168.1.6") is False


def test_cidr_matches_whole_network() -> None:
    allow = build_ip_allow_list(["192.168.1.0/24"])

    assert allow.allows("192.168.1.1") is True
    assert allow.allows("192.168.1.254") is True
    assert allow.allows("192.168.2.1") is False


def test_host_bits_in_cidr_are_tolerated() -> None:
    """写 192.168.1.5/24 的意图显然是「这个网段」，不按非法处理。"""
    allow = build_ip_allow_list(["192.168.1.5/24"])

    assert allow.invalid == ()
    assert allow.allows("192.168.1.7") is True


def test_loopback_is_always_allowed() -> None:
    """逃生通道：白名单里一个回环地址都没写，本机也必须能进。"""
    allow = build_ip_allow_list(["10.0.0.0/8"])

    for ip in ("127.0.0.1", "127.0.0.53", "::1", "localhost"):
        assert is_loopback(ip)
        assert allow.allows(ip) is True


def test_invalid_entry_never_matches_but_keeps_the_gate_closed() -> None:
    """乱码条目不等于「放行所有」：除本机外一律拒绝。"""
    allow = build_ip_allow_list(["这不是IP"])

    assert allow.enabled is True
    assert allow.invalid == ("这不是IP",)
    assert allow.networks == ()
    assert allow.allows("203.0.113.9") is False
    assert allow.allows("127.0.0.1") is True


def test_invalid_entries_do_not_disable_valid_ones() -> None:
    allow = build_ip_allow_list(["10.0.0.0/8", "oops", "192.168.1.5"])

    assert allow.invalid == ("oops",)
    assert allow.allows("10.1.2.3") is True
    assert allow.allows("192.168.1.5") is True
    assert allow.allows("8.8.8.8") is False


def test_ipv4_mapped_client_matches_ipv4_entry() -> None:
    """双栈套接字上 IPv4 客户端以 ::ffff:a.b.c.d 出现，必须还原后再匹配。"""
    allow = build_ip_allow_list(["192.168.1.0/24"])

    assert allow.allows("::ffff:192.168.1.5") is True


def test_ipv6_entry_and_scope_suffix() -> None:
    allow = build_ip_allow_list(["fd00::/8"])

    assert allow.allows("fd00::1") is True
    assert allow.allows("fd00::1%eth0") is True
    assert allow.allows("2001:db8::1") is False


def test_unparsable_client_ip_is_denied_when_enabled() -> None:
    allow = build_ip_allow_list(["10.0.0.0/8"])

    assert allow.allows("") is False
    assert allow.allows("unknown") is False


def test_entries_are_deduped_keeping_order() -> None:
    allow = build_ip_allow_list([" 10.0.0.1 ", "10.0.0.1", "", "  ", "10.0.0.2"])

    assert allow.entries == ("10.0.0.1", "10.0.0.2")


def test_describe_reports_entries_and_invalid() -> None:
    described = build_ip_allow_list(["192.168.1.0/24", "bad"]).describe()

    assert described == {
        "enabled": True,
        "entries": ["192.168.1.0/24", "bad"],
        "invalid": ["bad"],
    }


# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------


def test_config_normalizes_entries() -> None:
    config = DashboardConfig(allowed_ips=[" 10.0.0.5 ", "", "10.0.0.5", "  10.0.0.6"])

    assert config.allowed_ips == ["10.0.0.5", "10.0.0.6"]


def test_unparsable_entry_does_not_fail_validation() -> None:
    """刻意不抛错：抛错会让 validate_plugin_config 把整个字段回落成空列表（= 放开所有）。"""
    config = DashboardConfig(allowed_ips=["这不是IP"])

    assert config.allowed_ips == ["这不是IP"]


def test_default_is_empty_and_unrestricted() -> None:
    assert DashboardConfig().allowed_ips == []


def test_allowed_ips_apply_without_restart() -> None:
    """白名单必须声明为「运行期安全」：保存后由 config_consumer 原地刷新，不需重启。

    这里直接看声明（``hot_reload_policies``），分类逻辑（最长前缀、未登记按需重启）
    由 ``test_dashboard_config_consumer.py`` 覆盖。
    """
    consumer = DashboardConfigConsumer(DashboardPlugin())

    rules = {rule.path: rule for rule in consumer.hot_reload_policies}

    rule = rules["plugin.dashboard.allowed_ips"]
    assert rule.hot_reload is True, "白名单在每次请求时判定，应当可以原地生效"
    assert rule.reason


# ---------------------------------------------------------------------------
# 中间件与热更新（构造真实 DashboardServer，不监听端口）
# ---------------------------------------------------------------------------


class _Transport:
    def __init__(self, peer: tuple[str, int]) -> None:
        self._peer = peer

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return self._peer if name == "peername" else default


class _FakeRequest:
    """中间件只用到 path / method / headers / transport / remote。"""

    def __init__(self, path: str, *, peer_ip: str, method: str = "GET") -> None:
        self.path = path
        self.method = method
        self.headers: dict[str, str] = {}
        self.transport = _Transport((peer_ip, 51234))
        self.remote = peer_ip


def _make_server(
    tmp_path: Path,
    *,
    allowed_ips: list[str] | None = None,
    logger: Any = None,
) -> DashboardServer:
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    return DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", allowed_ips=list(allowed_ips or [])),
        data_dir=tmp_path / "data",
        logger=logger or _NullLogger(),
        adapter=None,
        plugin_control=None,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )


async def _ok_handler(request: Any) -> web.Response:
    return web.Response(text="ok")


async def test_middleware_rejects_ip_outside_allow_list(tmp_path: Path) -> None:
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    response = await server._auth_middleware(_FakeRequest("/api/overview", peer_ip="203.0.113.9"), _ok_handler)

    assert response.status == 403
    payload = json.loads(response.body)
    assert payload["allowed_ips"] is False
    assert "白名单" in payload["error"]


async def test_middleware_allows_ip_inside_allow_list(tmp_path: Path) -> None:
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    response = await server._auth_middleware(_FakeRequest("/api/auth/status", peer_ip="10.1.2.3"), _ok_handler)

    assert response.status == 200
    assert response.text == "ok"


async def test_middleware_always_allows_loopback(tmp_path: Path) -> None:
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    response = await server._auth_middleware(_FakeRequest("/api/auth/status", peer_ip="127.0.0.1"), _ok_handler)

    assert response.status == 200


async def test_middleware_blocks_static_assets_too(tmp_path: Path) -> None:
    """名单外的来源连 SPA 外壳与静态资源都拿不到，不只是在 API 上拦。"""
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    for path in ("/", "/assets/index.js", "/plugins", "/index.html"):
        response = await server._auth_middleware(_FakeRequest(path, peer_ip="203.0.113.9"), _ok_handler)
        assert response.status == 403, path


async def test_middleware_exempts_healthz(tmp_path: Path) -> None:
    """反向代理/监控常从名单外的机器探活，healthz 不拦。"""
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    response = await server._auth_middleware(_FakeRequest("/healthz", peer_ip="203.0.113.9"), _ok_handler)

    assert response.status == 200


async def test_middleware_denies_before_password_setup(tmp_path: Path) -> None:
    """未设密码时的「只允许本机」之外，白名单要更先一步生效。"""
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])

    response = await server._auth_middleware(
        _FakeRequest("/api/auth/setup", peer_ip="203.0.113.9", method="POST"), _ok_handler
    )

    assert response.status == 403
    assert json.loads(response.body)["allowed_ips"] is False


async def test_apply_runtime_config_rebuilds_allow_list(tmp_path: Path) -> None:
    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8"])
    denied = _FakeRequest("/api/auth/status", peer_ip="203.0.113.9")
    assert (await server._auth_middleware(denied, _ok_handler)).status == 403

    server.apply_runtime_config(DashboardConfig(host="127.0.0.1", allowed_ips=["203.0.113.0/24"]))

    assert (await server._auth_middleware(denied, _ok_handler)).status == 200
    assert server.describe()["allowed_ips"] == {
        "enabled": True,
        "entries": ["203.0.113.0/24"],
        "invalid": [],
    }


def test_invalid_entries_are_reported_at_startup(tmp_path: Path) -> None:
    logger = _RecordingLogger()

    server = _make_server(tmp_path, allowed_ips=["10.0.0.0/8", "oops"], logger=logger)

    assert server.ip_allow_list.invalid == ("oops",)
    assert any("oops" in message for message in logger.warnings)


def test_empty_allow_list_is_reported_as_disabled(tmp_path: Path) -> None:
    server = _make_server(tmp_path)

    assert isinstance(server.ip_allow_list, IpAllowList)
    assert server.describe()["allowed_ips"]["enabled"] is False
    assert server.describe()["allowed_ips"]["entries"] == []
