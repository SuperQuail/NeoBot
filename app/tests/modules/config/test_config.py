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
    assert "deepseek-v4-pro" in registry.names
    assert "deepseek-v4-flash-max" in registry.names
    assert "deepseek-v4-flash-high" in registry.names
    assert "deepseek-v4-flash-off" in registry.names
    assert "qwen3-vl-8b" not in registry.names
    assert "cosyvoice2" not in registry.names
    assert "flux-schnell" not in registry.names


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
async def test_reload_success_reports_hot_and_restart_items(monkeypatch):
    """重载成功后必须报告：哪些改动立即生效、哪些需要重启。"""
    from neobot_app.config.proxy import ConfigProxy
    from neobot_app.config.schemas.bot import BotConfig

    reload_calls: list[int] = []

    class _FakeConfig:
        def __init__(self) -> None:
            self.inner = BotConfig()
            self.proxy = ConfigProxy(self.inner)

        def reload(self, config) -> None:
            reload_calls.append(1)
            # 模拟真实 ConfigProxy：替换内部配置对象
            self.inner = config
            self.proxy.reload(config)

        def __getattr__(self, name):
            return getattr(self.proxy, name)

    new_config = BotConfig()
    new_config.chat.group_chat_chance = 0.9
    new_config.tts.enabled = not new_config.tts.enabled
    monkeypatch.setattr(
        "neobot_app.bootstrap._config._load_config", lambda: new_config
    )
    monkeypatch.setattr(
        "neobot_app.bootstrap._pipeline.sync_data_files", lambda *a, **k: None
    )
    host = _FakeHost()
    config = _FakeConfig()

    _pipeline.register_config_reload_command(host_facade=host, config=config)
    result = await host.commands.handlers["config.reload"]()

    assert result["status"] == "ok"
    changes = result["changes"]
    hot_paths = {item["path"] for item in changes["hot_reload"]}
    restart_paths = {item["path"] for item in changes["needs_restart"]}
    assert "chat.group_chat_chance" in hot_paths
    assert "tts.enabled" in restart_paths
    assert "1 项立即生效" in result["message"]
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
        "[[models.registry]]\n"
        'key = "deepseek-v4-pro"\n'
        'description = "主对话模型（Agent模型编号0）"\n'
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-v4-pro"\n'
        "[models.registry.settings]\n"
        "deepseek_random_thinking_probability = 2.5\n"
        'deepseek_reasoning_effort = "high"\n'
        "\n"
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-max"\n'
        'description = "Agent模型编号1"\n'
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-v4-flash"\n'
        "[models.registry.settings]\n"
        'deepseek_reasoning_effort = "max"\n'
        "\n"
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-high"\n'
        'description = "Agent模型编号2"\n'
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-v4-flash"\n'
        "\n"
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-off"\n'
        'description = "Agent模型编号3"\n'
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-v4-flash"\n'
        "[models.registry.settings]\n"
        'deepseek_thinking_mode = "disabled"\n',
        encoding="utf-8",
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)

    # Assert
    assert config_obj.bot.account == 10001
    registry = get_model_registry()
    expected_models = {
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash-max": "deepseek-v4-flash",
        "deepseek-v4-flash-high": "deepseek-v4-flash",
        "deepseek-v4-flash-off": "deepseek-v4-flash",
    }
    assert set(registry.names) == set(expected_models)
    for key, model_name in expected_models.items():
        registered = registry.get(key)
        assert registered.provider_name == "DeepSeek"
        assert registered.model_name == model_name
        assert registered.base_url == _DEEPSEEK_KEYS["DeepSeek_URL"]
        assert registered.api_key == _DEEPSEEK_KEYS["DeepSeek_APIKey"]
    assert "Agent模型编号0" in registry.get("deepseek-v4-pro").description
    primary_extra = registry.get("deepseek-v4-pro").settings.extra_body
    assert primary_extra["__deepseek_reasoning_effort__"] == "high"
    assert primary_extra["__deepseek_random_thinking_probability__"] == 1.0
    assert primary_extra["__deepseek_thinking_mode__"] == "true"
    assert (
        registry.get("deepseek-v4-flash-max").settings.extra_body[
            "__deepseek_reasoning_effort__"
        ]
        == "max"
    )
    assert (
        registry.get("deepseek-v4-flash-off").settings.extra_body[
            "__deepseek_thinking_mode__"
        ]
        == "false"
    )
    assert registry.get("deepseek-v4-flash-high").settings.extra_body[
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
        "[models.assignments]\n"
        'primary_chat_model = "deepseek-v4-pro"\n'
        'agent_model_1 = "deepseek-v4-flash-max"\n'
        'agent_model_2 = "deepseek-v4-flash-high"\n'
        'agent_model_3 = "deepseek-v4-flash-off"\n'
        'vision_model = ""\n'
        'tts_model = ""\n'
        "creator_image_models = []\n"
        "\n"
        "[[models.registry]]\n"
        'key = "deepseek-v4-pro"\n'
        'provider = ""\n'
        'model_name = ""\n'
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-max"\n'
        'provider = ""\n'
        'model_name = ""\n'
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-high"\n'
        'provider = ""\n'
        'model_name = ""\n'
        "[[models.registry]]\n"
        'key = "deepseek-v4-flash-off"\n'
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
    expected = {
        "deepseek-v4-pro": "primary_chat_model",
        "deepseek-v4-flash-max": "agent_model_1",
        "deepseek-v4-flash-high": "agent_model_2",
        "deepseek-v4-flash-off": "agent_model_3",
    }
    for key, role in expected.items():
        assert f"模型 {key}（{role}）缺少: provider 配置、model_name 配置" in message
    assert message.count("缺少: provider 配置、model_name 配置") == 4
    assert "缺少: 平台" not in message
    assert "APIKey" not in message
    assert "qwen3-vl-8b" not in message
    assert "cosyvoice2" not in message
    assert "flux-schnell" not in message
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


def test_migrations_registered_and_applied_on_load(monkeypatch, tmp_path):
    """迁移必须在 Config.load 时注册并链式生效(0.3.0 -> 0.4.0 -> 0.5.0),防止迁移成为死代码。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.3.0"\n'
        "[bot]\naccount = 10001\n\n"
        "[chat]\n"
        'group_prompt_template = "旧群聊模板"\n'
        'friend_prompt_template = "旧私聊模板"\n'
        'long_reply_fallback_template = "旧兜底"\n'
        'group_chat_resume_prompt_template = "旧恢复"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)

    # Assert
    assert config_obj.version == "0.6.0"
    assert not hasattr(config_obj.chat, "group_prompt_template")
    assert config_obj.bot.bot_data, "bot_data 必须保留"
    raw = cfg_path.read_text(encoding="utf-8")
    assert "group_prompt_template" not in raw
    assert 'version = "0.6.0"' in raw


def test_migration_v4_to_v5_moves_console_and_image_models(monkeypatch, tmp_path):
    """0.4.0 -> 0.5.0: [console] 迁到 [dashboard]，生图模型迁移为列表。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.4.0"\n'
        '[bot]\naccount = 10001\n\n'
        '[console]\n'
        'enabled = true\n'
        'host = "127.0.0.1"\n'
        'port = 9000\n'
        'admin_enabled = false\n'
        'admin_port = 9891\n'
        'port_search_limit = 50\n\n'
        '[models.creator_image_model]\n'
        'description = "旧生图模型"\n'
        'provider = "SiliconFlow"\n'
        'model_name = "black-forest-labs/FLUX.1-schnell"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)

    # Assert
    assert config_obj.version == "0.6.0"
    assert config_obj.dashboard.enabled is True
    assert config_obj.dashboard.host == "127.0.0.1"
    assert config_obj.dashboard.port == 9000
    assert not hasattr(config_obj, "console")
    image_keys = config_obj.models.assignments.creator_image_models
    assert image_keys == ["black-forest-labs-FLUX.1-schnell"]
    image_model = config_obj.models.get(image_keys[0])
    assert image_model is not None
    assert image_model.description == "旧生图模型"
    assert image_model.model_name == "black-forest-labs/FLUX.1-schnell"
    raw = cfg_path.read_text(encoding="utf-8")
    assert "[console]" not in raw
    assert "[dashboard]" in raw
    assert "[[models.registry]]" in raw
    assert "[models.assignments]" in raw
    assert "[[models.creator_image_models]]" not in raw
