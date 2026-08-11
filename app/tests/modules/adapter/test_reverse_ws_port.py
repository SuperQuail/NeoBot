"""反向 WebSocket 端口配置链路测试(生产环境回归)。

场景:生产 .env 用 NEOBOT_LOCAL_ADAPTER_PORT=8091 配置端口,但实际跑
onebot 模式(反向 WS)。历史上该变量只对 local 模式生效,onebot 反向
WS 静默回落默认 8080 —— 修复后应正确生效。
"""

from __future__ import annotations

import pytest


class _FakeAdapterCfg:
    mode = "onebot"
    local_host = "127.0.0.1"
    local_port = 8090
    local_auth_token = ""
    reverse_ws_host = ""
    reverse_ws_port = 0


class _FakeBotCfg:
    account = 12345
    nick_name = "弥音"


class _FakeConfig:
    def __init__(self) -> None:
        self.adapter = _FakeAdapterCfg()
        self.bot = _FakeBotCfg()


def _settings(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from neobot_app.assembly.adapter import _settings_from_config

    return _settings_from_config(_FakeConfig())


def test_onebot_reverse_ws_port_from_local_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产配置:NEOBOT_LOCAL_ADAPTER_PORT=8091,onebot 模式应监听 8091。"""
    settings = _settings(monkeypatch, {"NEOBOT_LOCAL_ADAPTER_PORT": "8091"})
    assert settings.mode == "onebot"
    assert settings.reverse_ws_port == 8091


def test_standard_env_var_takes_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    """标准键 NEO_BOT_ADAPTER_PORT 优先于兼容回退。"""
    settings = _settings(
        monkeypatch,
        {
            "NEO_BOT_ADAPTER_PORT": "8092",
            "NEOBOT_ADAPTER_PORT": "8091",
            "NEOBOT_LOCAL_ADAPTER_PORT": "8090",
        },
    )
    assert settings.reverse_ws_port == 8092


def test_legacy_env_var_without_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """老版本无 Local 字样的键(NEOBOT_ADAPTER_PORT)兼容。"""
    settings = _settings(monkeypatch, {"NEOBOT_ADAPTER_PORT": "8091"})
    assert settings.reverse_ws_port == 8091


def test_env_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """.env 键名大小写任意(load_env 原样保留)也能生效。"""
    settings = _settings(monkeypatch, {"neobot_local_adapter_port": "8091"})
    assert settings.reverse_ws_port == 8091


def test_reverse_ws_host_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        {"NEOBOT_LOCAL_ADAPTER_HOST": "127.0.0.1"},
    )
    assert settings.reverse_ws_host == "127.0.0.1"


def test_settings_reach_core(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置链路终点:OneBotAdapter 的 core 拿到端口。"""
    from neobot_adapter import AdapterSettings, create_adapter

    adapter = create_adapter(
        AdapterSettings(mode="onebot", reverse_ws_host="127.0.0.1", reverse_ws_port=8091)
    )
    assert adapter.core.host == "127.0.0.1"
    assert adapter.core.port == 8091


def test_unset_keeps_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置任何环境变量:reverse_ws 保持未配置(由 core 回落默认 8080)。"""
    monkeypatch.delenv("NEOBOT_LOCAL_ADAPTER_PORT", raising=False)
    monkeypatch.delenv("NEO_BOT_ADAPTER_PORT", raising=False)
    settings = _settings(monkeypatch, {})
    assert settings.reverse_ws_port == 0
    assert settings.reverse_ws_host == ""


def test_local_mode_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """local 模式仍用 local_* 字段(不受反向 WS 链路影响)。"""
    monkeypatch.setattr(_FakeAdapterCfg, "mode", "local")
    settings = _settings(monkeypatch, {"NEOBOT_LOCAL_ADAPTER_PORT": "8091"})
    assert settings.mode == "local"
    assert settings.local_port == 8091
