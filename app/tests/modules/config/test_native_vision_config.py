from __future__ import annotations

from unittest.mock import Mock

import pytest
import tomlkit

from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass

from neobot_app.bootstrap import _providers
from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig, ModelRegistration
from neobot_chat import get_model_registry
from neobot_chat.providers.native_vision import NativeVisionFallbackProvider


class FakeProvider:
    def __init__(self, native_vision=False):
        self.native_vision = native_vision
        self.model = "vision" if native_vision else "text"

    async def chat(self, messages, tools=None):
        return {"role": "assistant", "content": "ok"}

    async def close(self):
        pass


def test_native_vision_defaults_are_backwards_compatible():
    config = BotConfig()
    assert ModelRegistration().native_vision is False
    assert config.models.primary_chat_model.native_vision is False
    assert config.agent_model.main_agent_vision_fallback == 1
    assert config.chat.native_vision_default_image_count == 4


def test_config_registration_passes_native_vision(monkeypatch):
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "test-key")
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True
    config.models.primary_chat_model.model_name = "deepseek-v4-flash-vision-exp"
    registry = get_model_registry()
    saved = registry.items()
    try:
        Config.register_models(config)
        main = registry.get("primary_chat_model")
        assert main.native_vision
        assert main.create_provider().native_vision
        assert not registry.get("agent_model_1").native_vision
    finally:
        registry.clear()
        for _, model in saved:
            registry.register(model)


async def test_bootstrap_wraps_configured_main_and_text_fallback(monkeypatch):
    config = BotConfig()
    config.agent_model.main_agent = 2
    config.agent_model.main_agent_vision_fallback = 3
    config.models.agent_model_2.native_vision = True
    created = []

    def create(name):
        created.append(name)
        return FakeProvider(name == "agent_model_2")

    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert isinstance(provider, NativeVisionFallbackProvider)
    assert provider.native_vision
    assert set(created) == {"agent_model_2", "agent_model_3"}
    await provider.close()


@pytest.mark.parametrize("index", [0, 4, -1, "1", True])
def test_invalid_fallback_route_is_explicit_startup_error(monkeypatch, index):
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True
    config.agent_model.main_agent_vision_fallback = index
    create = Mock()
    monkeypatch.setattr(_providers, "create_provider", create)
    logger = Mock()
    provider, error = _providers.build_main_provider(config=config, logger=logger)
    assert provider is None
    assert "回退配置无效" in error
    create.assert_not_called()
    logger.error.assert_called_once()


def test_fallback_must_be_nonvision(monkeypatch):
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True
    config.models.agent_model_1.native_vision = True
    create = Mock()
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert provider is None
    assert "native_vision=false" in error
    create.assert_not_called()


@pytest.mark.parametrize("failure", ["creation", "capability"])
async def test_unavailable_primary_falls_back_at_startup_with_notice(monkeypatch, failure):
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True

    def create(name):
        if name == "primary_chat_model" and failure == "creation":
            raise ValueError("unavailable")
        return FakeProvider()

    monkeypatch.setattr(_providers, "create_provider", create)
    logger = Mock()
    provider, error = _providers.build_main_provider(config=config, logger=logger)
    assert error is None
    assert not provider.native_vision
    response = await provider.chat([{"role": "user", "content": "hi"}])
    notice = response["extensions"]["native_vision_fallback"]
    assert notice["to_model"] == "agent_model_1"
    assert notice["from_model"] == "primary_chat_model"
    assert "不能声称" in notice["notice"]
    assert logger.error.called
    await provider.close()


def test_nonvision_main_does_not_create_fallback(monkeypatch):
    config = BotConfig()
    create = Mock(return_value=FakeProvider())
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert not isinstance(provider, NativeVisionFallbackProvider)
    create.assert_called_once_with("primary_chat_model")


def test_unavailable_fallback_is_startup_error(monkeypatch):
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True
    create = Mock(side_effect=ValueError("missing key"))
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert provider is None
    assert "回退 provider(agent_model_1)" in error
    create.assert_called_once_with("agent_model_1")


@pytest.mark.parametrize("count", [0, 4, 9])
def test_native_vision_image_count_toml_roundtrip(count):
    data = tomlkit.parse(f'[chat]\nnative_vision_default_image_count = {count}\n').unwrap()
    document, _, _ = dataclass_to_toml(BotConfig, existing_data=data)
    parsed = tomlkit.parse(tomlkit.dumps(document)).unwrap()
    config = dict_to_dataclass(parsed, BotConfig)
    assert config.chat.native_vision_default_image_count == count
    assert "手动加图工具不受此数量限制" in tomlkit.dumps(document)


def test_native_vision_toml_conversion_roundtrip():
    data = tomlkit.parse(
        '[models.primary_chat_model]\n'
        'model_name = "deepseek-v4-flash-vision-exp"\n'
        'native_vision = true\n'
        '[agent_model]\nmain_agent_vision_fallback = 2\n'
    ).unwrap()
    document, _, _ = dataclass_to_toml(BotConfig, existing_data=data)
    parsed = tomlkit.parse(tomlkit.dumps(document)).unwrap()
    config = dict_to_dataclass(parsed, BotConfig)
    assert config.models.primary_chat_model.native_vision is True
    assert config.models.primary_chat_model.model_name == "deepseek-v4-flash-vision-exp"
    assert config.agent_model.main_agent_vision_fallback == 2
    assert config.models.agent_model_2.native_vision is False


def test_native_vision_toml_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "test-key")
    path = tmp_path / "bot.toml"
    path.write_text(
        '[models.primary_chat_model]\n'
        'model_name = "deepseek-v4-flash-vision-exp"\n'
        'native_vision = true\n'
        '[agent_model]\nmain_agent_vision_fallback = 2\n',
        encoding="utf-8",
    )
    registry = get_model_registry()
    saved = registry.items()
    try:
        config = Config.load(path, BotConfig)
        assert config.models.primary_chat_model.native_vision is True
        assert config.agent_model.main_agent_vision_fallback == 2
        assert registry.get("primary_chat_model").native_vision
        reloaded = Config.load(path, BotConfig)
        assert reloaded.models.primary_chat_model.native_vision is True
        assert reloaded.agent_model.main_agent_vision_fallback == 2
        assert reloaded.models.agent_model_2.native_vision is False
    finally:
        registry.clear()
        for _, model in saved:
            registry.register(model)
