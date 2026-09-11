"""启动期行为：配置缺失不再退出，改为默认配置 + 启动即待机。"""

from __future__ import annotations

import pytest

from neobot_app import bootstrap
from neobot_app.runtime.standby_service import RUNNING, StandbyService, STANDBY


def test_set_startup_reason_only_when_standby() -> None:
    service = StandbyService(start_in_standby=True)

    service.set_startup_reason("配置缺失，已进入待机等待修复：boom")

    assert service.state == STANDBY
    assert "配置缺失" in service.status()["reason"]

    running = StandbyService()
    running.set_startup_reason("不该生效")
    assert running.state == RUNNING
    assert running.status()["reason"] == ""


def test_config_failure_falls_back_to_defaults(monkeypatch) -> None:
    bootstrap.enable_core_reuse()
    bootstrap._CORE_CACHE["config"] = "旧的兜底配置"

    def boom():
        raise RuntimeError("config.toml 解析失败")

    monkeypatch.setattr(bootstrap, "build_config", boom)
    try:
        config = bootstrap._load_config_or_defaults()

        assert bootstrap.config_load_error().startswith("RuntimeError:")
        from neobot_app.config.proxy import ConfigProxy
        from neobot_app.config.schemas.bot import BotConfig

        # 兜底同样包成 ConfigProxy：配置损坏时面板/QQ 的「配置重载」仍要能跑
        assert isinstance(config, ConfigProxy), "应返回默认配置以便拉起面板"
        assert isinstance(config._inner, BotConfig)
        assert "config" not in bootstrap._CORE_CACHE, "失败时不得缓存兜底配置"
    finally:
        bootstrap.disable_core_reuse()
        monkeypatch.setattr(bootstrap, "_CONFIG_ERROR", "", raising=False)


def test_config_fallback_not_recached_through_reuse(monkeypatch) -> None:
    """软重启路径：兜底默认值不得被 _reuse_or 写回缓存，修好配置必须能读到。"""
    bootstrap.enable_core_reuse()
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("config.toml 解析失败")

    monkeypatch.setattr(bootstrap, "build_config", boom)
    try:
        first = bootstrap._load_config_for_reuse()
        from neobot_app.config.proxy import ConfigProxy

        assert isinstance(first, ConfigProxy)
        assert bootstrap.get_cached_core("config") is None, "兜底配置不得留在缓存里"

        # 用户修好文件后再点软重启：必须重新读文件，而不是复用兜底
        monkeypatch.setattr(bootstrap, "build_config", lambda: "修复后的配置")
        second = bootstrap._load_config_for_reuse()

        assert second == "修复后的配置"
        assert calls["n"] == 1
    finally:
        bootstrap.disable_core_reuse()
        monkeypatch.setattr(bootstrap, "_CONFIG_ERROR", "", raising=False)


def test_config_success_clears_previous_error(monkeypatch) -> None:
    bootstrap.enable_core_reuse()
    monkeypatch.setattr(bootstrap, "_CONFIG_ERROR", "上一次失败", raising=False)
    monkeypatch.setattr(bootstrap, "build_config", lambda: {"loaded": True})
    try:
        config = bootstrap._load_config_or_defaults()

        assert config == {"loaded": True}
        assert bootstrap.config_load_error() == ""
    finally:
        bootstrap.disable_core_reuse()


@pytest.mark.asyncio
async def test_standby_without_onebot_connection() -> None:
    """未连接 OneBot 也必须能待机（面板可用来改配置）。"""
    service = StandbyService(connect_onebot=False)
    service.set_hooks(on_enter=None, on_resume=None, on_onebot_change=None)

    ok, _ = await service.enter(reason="本地调试")

    assert ok is True and service.is_standby() is True
    assert service.connect_onebot is False
