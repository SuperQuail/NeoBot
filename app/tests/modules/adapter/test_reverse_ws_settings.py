"""反向 WebSocket 监听设置值对象的解析规则测试。

这些用例把「构造参数 > 环境变量 > 默认值」的优先级、token 归一化、
以及「未配置 token 却对外监听」的告警判定**锁死在值对象这一层**：
`AdapterCore` 不再自己解析配置，规则只有这一处实现。
"""

from __future__ import annotations

import pytest

from neobot_adapter.onebot.receiver.settings import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ReverseWsSettings,
    env_ci,
)


# ── 解析优先级 ──────────────────────────────────────────────────────


def test_defaults_when_nothing_configured() -> None:
    settings = ReverseWsSettings.resolve(environ={})
    assert settings.host == DEFAULT_HOST
    assert settings.port == DEFAULT_PORT
    assert settings.access_token == ""


def test_explicit_values_win_over_env() -> None:
    settings = ReverseWsSettings.resolve(
        host="127.0.0.1",
        port=8091,
        environ={"NEO_BOT_ADAPTER_HOST": "10.0.0.1", "NEO_BOT_ADAPTER_PORT": "9999"},
    )
    assert settings.host == "127.0.0.1"
    assert settings.port == 8091


def test_env_used_when_argument_absent() -> None:
    settings = ReverseWsSettings.resolve(
        environ={"NEO_BOT_ADAPTER_HOST": "10.0.0.1", "NEO_BOT_ADAPTER_PORT": "9999"}
    )
    assert settings.host == "10.0.0.1"
    assert settings.port == 9999


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"NEO_BOT_ADAPTER_PORT": "8092"}, 8092),
        ({"NEOBOT_ADAPTER_PORT": "8091"}, 8091),
        ({"NEOBOT_LOCAL_ADAPTER_PORT": "8090"}, 8090),
        (
            {
                "NEO_BOT_ADAPTER_PORT": "8092",
                "NEOBOT_ADAPTER_PORT": "8091",
                "NEOBOT_LOCAL_ADAPTER_PORT": "8090",
            },
            8092,
        ),
    ],
)
def test_port_env_compatibility_chain(env: dict[str, str], expected: int) -> None:
    """规范键 > 迁移期老键 > local 专用键。"""
    assert ReverseWsSettings.resolve(environ=env).port == expected


def test_host_env_compatibility_chain() -> None:
    assert (
        ReverseWsSettings.resolve(
            environ={"NEOBOT_LOCAL_ADAPTER_HOST": "127.0.0.1"}
        ).host
        == "127.0.0.1"
    )


def test_env_lookup_is_case_insensitive() -> None:
    """`.env` 键名原样保留，大小写任意都要生效。"""
    settings = ReverseWsSettings.resolve(
        environ={"neobot_local_adapter_port": "8091"}
    )
    assert settings.port == 8091
    assert env_ci({"NeoBot_Local_Adapter_Port": "8091"}, "NEOBOT_LOCAL_ADAPTER_PORT") == (
        "8091"
    )


def test_blank_env_values_fall_through_to_default() -> None:
    assert ReverseWsSettings.resolve(environ={"NEO_BOT_ADAPTER_PORT": ""}).port == (
        DEFAULT_PORT
    )
    assert ReverseWsSettings.resolve(environ={"NEO_BOT_ADAPTER_HOST": ""}).host == (
        DEFAULT_HOST
    )


# ── token 归一化与安全告警 ──────────────────────────────────────────


def test_token_is_stripped() -> None:
    assert ReverseWsSettings.resolve(access_token="  s3cret  ").access_token == "s3cret"


def test_blank_token_is_normalized_to_empty() -> None:
    assert ReverseWsSettings.resolve(access_token="   ").access_token == ""
    assert ReverseWsSettings.resolve(access_token="   ").token_enabled is False


def test_warning_when_open_to_network_without_token() -> None:
    settings = ReverseWsSettings.resolve(host="0.0.0.0", port=8080)
    assert settings.exposes_non_loopback_without_token is True
    warning = settings.security_warning()
    assert warning is not None
    assert "0.0.0.0:8080" in warning
    assert "reverse_ws_access_token" in warning


def test_no_warning_when_token_configured() -> None:
    settings = ReverseWsSettings.resolve(
        host="0.0.0.0", port=8080, access_token="s3cret"
    )
    assert settings.exposes_non_loopback_without_token is False
    assert settings.security_warning() is None


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.53", "localhost", "::1"])
def test_no_warning_on_loopback_without_token(host: str) -> None:
    assert ReverseWsSettings.resolve(host=host).security_warning() is None


# ── 展示 ────────────────────────────────────────────────────────────


def test_describe_reports_token_state() -> None:
    assert "已启用" in ReverseWsSettings.resolve(access_token="t").describe()
    assert "未启用" in ReverseWsSettings.resolve().describe()
    assert "ws://0.0.0.0:8080" in ReverseWsSettings.resolve().describe()


def test_settings_are_hashable_and_comparable() -> None:
    """值对象语义：同值可比、可去重（控制面据此判断是否需要重建监听）。"""
    first = ReverseWsSettings.resolve(host="127.0.0.1", port=8091)
    second = ReverseWsSettings.resolve(host="127.0.0.1", port=8091)
    assert first == second
    assert len({first, second}) == 1
