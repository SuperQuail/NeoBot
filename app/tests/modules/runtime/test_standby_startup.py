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
        from neobot_app.config.schemas.bot import BotConfig

        assert isinstance(config, BotConfig), "应返回默认配置以便拉起面板"
        assert "config" not in bootstrap._CORE_CACHE, "失败时不得缓存兜底配置"
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
