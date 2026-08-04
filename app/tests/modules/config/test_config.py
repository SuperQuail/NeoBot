from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import tomlkit

from neobot_app.bootstrap import _pipeline
from neobot_app.config.loader.manager import Config, ConfigLoadError
from neobot_app.config.schemas.bot import BotConfig
from neobot_chat import get_model_registry

_DEEPSEEK_KEYS = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test-1234567890",
}


def _clear_platform_env(monkeypatch) -> None:
    for key in (
        "DeepSeek_URL",
        "DeepSeek_APIKey",
        "SiliconFlow_URL",
        "SiliconFlow_APIKey",
        "HuoShan_APIKey",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_minimal_config(tmp_path) -> Path:
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text('[bot]\naccount = 10001\n\n[chat]\n', encoding="utf-8")
    return cfg_path


def test_load_missing_required_keys_raises_with_full_list(monkeypatch, tmp_path):
    _clear_platform_env(monkeypatch)
    cfg_path = _write_minimal_config(tmp_path)
    exited: list[int] = []
    monkeypatch.setattr("sys.exit", lambda code: exited.append(code))

    with pytest.raises(ConfigLoadError) as exc_info:
        Config.load(cfg_path, BotConfig)

    message = str(exc_info.value)
    assert "primary_chat_model" in message
    assert "agent_model_1" in message
    assert "agent_model_3" in message
    assert "DeepSeek_APIKey" in message
    assert "vision_model" not in message
    assert "tts_model" not in message
    assert exited == []


def test_load_missing_only_optional_platform_keys_succeeds(monkeypatch, tmp_path):
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = _write_minimal_config(tmp_path)

    config_obj = Config.load(cfg_path, BotConfig)

    assert config_obj.bot.account == 10001
    registry = get_model_registry()
    assert "primary_chat_model" in registry.names
    assert "agent_model_1" in registry.names
    assert "agent_model_2" in registry.names
    assert "agent_model_3" in registry.names
    assert "vision_model" not in registry.names
    assert "tts_model" not in registry.names
    assert "creator_image_model" not in registry.names


def test_load_missing_key_never_calls_sys_exit_even_with_tts_enabled(
    monkeypatch, tmp_path
):
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        '[bot]\naccount = 10001\n\n[chat]\n\n[tts]\nenabled = true\n',
        encoding="utf-8",
    )
    exited: list[int] = []
    monkeypatch.setattr("sys.exit", lambda code: exited.append(code))

    config_obj = Config.load(cfg_path, BotConfig)

    assert config_obj.tts.enabled is True
    assert "tts_model" not in get_model_registry().names
    assert exited == []


class _FakeCommands:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def register(self, name: str, description: str, handler) -> None:
        self.handlers[name] = handler


class _FakeLifecycle:
    def __init__(self) -> None:
        self.fired: list[str] = []

    async def fire(self, stage: str, **kwargs) -> None:
        self.fired.append(stage)


class _FakeHost:
    def __init__(self) -> None:
        self.commands = _FakeCommands()
        self.lifecycle = _FakeLifecycle()


@pytest.mark.asyncio
async def test_reload_missing_key_keeps_old_config(monkeypatch):
    reload_calls: list[int] = []

    class _FakeConfig:
        def reload(self, config) -> None:
            reload_calls.append(1)

    def _boom():
        raise ConfigLoadError(
            "配置校验失败，以下必需配置缺失：\n  - 模型 primary_chat_model 缺少: 平台 DeepSeek_APIKey 配置"
        )

    monkeypatch.setattr("neobot_app.bootstrap._config._load_config", _boom)
    monkeypatch.setattr(
        "neobot_app.bootstrap._pipeline.sync_data_files", lambda *a, **k: None
    )
    host = _FakeHost()
    config = _FakeConfig()

    _pipeline.register_config_reload_command(host_facade=host, config=config)
    result = await host.commands.handlers["config.reload"]()

    assert result["status"] == "error"
    assert "配置重载失败" in result["message"]
    assert "primary_chat_model" in result["message"]
    assert reload_calls == []
    assert host.lifecycle.fired == []


@pytest.mark.asyncio
async def test_reload_success_reports_restart_required_items(monkeypatch):
    reload_calls: list[int] = []

    class _FakeConfig:
        def reload(self, config) -> None:
            reload_calls.append(1)

    monkeypatch.setattr("neobot_app.bootstrap._config._load_config", lambda: object())
    monkeypatch.setattr(
        "neobot_app.bootstrap._pipeline.sync_data_files", lambda *a, **k: None
    )
    host = _FakeHost()
    config = _FakeConfig()

    _pipeline.register_config_reload_command(host_facade=host, config=config)
    result = await host.commands.handlers["config.reload"]()

    assert result["status"] == "ok"
    assert "已生效" in result["message"]
    assert "需重启" in result["message"]
    assert reload_calls == [1]
    assert host.lifecycle.fired == ["config.changed"]


def test_load_only_deepseek_key_registers_chat_models_with_details(monkeypatch, tmp_path):
    """仅配置 DeepSeek 平台环境变量时，四个对话模型必须注册且 base_url/api_key/extra_body 完整正确。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        "[bot]\n"
        "account = 10001\n"
        "\n"
        "[chat]\n"
        "\n"
        "[models.primary_chat_model.settings]\n"
        "deepseek_random_thinking_probability = 2.5\n"
        "deepseek_reasoning_effort = \"high\"\n",
        encoding="utf-8",
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)

    # Assert
    assert config_obj.bot.account == 10001
    registry = get_model_registry()
    expected_models = {
        "primary_chat_model": "deepseek-v4-pro",
        "agent_model_1": "deepseek-v4-flash",
        "agent_model_2": "deepseek-v4-flash",
        "agent_model_3": "deepseek-v4-flash",
    }
    assert set(registry.names) == set(expected_models)
    for name, model_name in expected_models.items():
        registered = registry.get(name)
        assert registered.provider_name == "DeepSeek"
        assert registered.model_name == model_name
        assert registered.base_url == _DEEPSEEK_KEYS["DeepSeek_URL"]
        assert registered.api_key == _DEEPSEEK_KEYS["DeepSeek_APIKey"]
        assert "Agent模型编号0" in registry.get("primary_chat_model").description
    primary_extra = registry.get("primary_chat_model").settings.extra_body
    assert primary_extra["__deepseek_reasoning_effort__"] == "high"
    assert primary_extra["__deepseek_random_thinking_probability__"] == 1.0
    assert primary_extra["__deepseek_thinking_mode__"] == "true"
    assert (
        registry.get("agent_model_1").settings.extra_body[
            "__deepseek_reasoning_effort__"
        ]
        == "max"
    )
    assert (
        registry.get("agent_model_3").settings.extra_body[
            "__deepseek_thinking_mode__"
        ]
        == "false"
    )
    assert registry.get("agent_model_2").settings.extra_body[
        "__deepseek_random_thinking_probability__"
    ] == 0.6


def test_load_missing_items_reports_exact_full_list_with_multiple_reasons(
    monkeypatch, tmp_path
):
    """chat 模型 provider/model_name 同时为空时，错误消息必须完整列出全部 4 个缺失项且不误报平台 Key。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        "[models.primary_chat_model]\n"
        'provider = ""\n'
        'model_name = ""\n'
        "[models.agent_model_1]\n"
        'provider = ""\n'
        'model_name = ""\n'
        "[models.agent_model_2]\n"
        'provider = ""\n'
        'model_name = ""\n'
        "[models.agent_model_3]\n"
        'provider = ""\n'
        'model_name = ""\n',
        encoding="utf-8",
    )
    exited: list[int] = []
    monkeypatch.setattr("sys.exit", lambda code: exited.append(code))

    # Act
    with pytest.raises(ConfigLoadError) as exc_info:
        Config.load(cfg_path, BotConfig)

    # Assert
    message = str(exc_info.value)
    for model_name in (
        "primary_chat_model",
        "agent_model_1",
        "agent_model_2",
        "agent_model_3",
    ):
        assert f"模型 {model_name} 缺少: provider 配置、model_name 配置" in message
    assert "缺少: 平台" not in message
    assert "APIKey" not in message
    assert "vision_model" not in message
    assert "tts_model" not in message
    assert "creator_image_model" not in message
    assert exited == []


def test_load_damaged_toml_is_regenerated_as_valid_config(monkeypatch, tmp_path):
    """损坏的 TOML 必须被覆盖重建为合法配置，缺 Key 时仍抛 ConfigLoadError 且文件可重新解析。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text("this is {{{ not valid toml", encoding="utf-8")
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )

    # Act
    with pytest.raises(ConfigLoadError):
        Config.load(cfg_path, BotConfig)

    # Assert
    doc = tomlkit.parse(cfg_path.read_text(encoding="utf-8")).unwrap()
    assert "bot" in doc
    assert "chat" in doc
    assert "models" in doc
    assert doc["bot"]["account"] == 0


def test_load_invalid_type_value_falls_back_to_default_and_rewrites(monkeypatch, tmp_path):
    """类型不匹配的配置值（account 为字符串）必须回退为默认值并把合法默认写入文件。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        '[bot]\naccount = "not-an-int"\n\n[chat]\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)

    # Assert
    assert config_obj.bot.account == 0
    doc = tomlkit.parse(cfg_path.read_text(encoding="utf-8")).unwrap()
    assert doc["bot"]["account"] == 0
