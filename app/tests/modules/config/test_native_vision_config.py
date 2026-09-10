from __future__ import annotations

import dataclasses
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
    assert config.chat.native_vision_default_image_count == 4
    # 回退目标固定为视觉模型，不再需要用户手选回退模型编号
    assert "main_agent_vision_fallback" not in {
        f.name for f in dataclasses.fields(config.agent_model)
    }


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


async def test_bootstrap_wraps_main_with_vision_model_fallback(monkeypatch):
    """主模型声明原生视觉时，回退路由固定为视觉模型 vision_model。"""
    config = BotConfig()
    config.agent_model.main_agent = 2
    config.models.agent_model_2.native_vision = True
    created = []

    def create(name):
        created.append(name)
        return FakeProvider(native_vision=True)

    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert isinstance(provider, NativeVisionFallbackProvider)
    assert provider.native_vision
    assert created == ["agent_model_2", "vision_model"]
    await provider.close()


@pytest.mark.parametrize("failure", ["creation", "capability"])
async def test_unavailable_primary_falls_back_to_vision_model(monkeypatch, failure):
    """主模型不可用（创建失败或无视觉能力）时自动切换到视觉模型，图片照常发送。"""
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True

    def create(name):
        if name == "primary_chat_model" and failure == "creation":
            raise ValueError("unavailable")
        if name == "vision_model":
            return FakeProvider(native_vision=True)
        return FakeProvider(native_vision=False)

    monkeypatch.setattr(_providers, "create_provider", create)
    logger = Mock()
    provider, error = _providers.build_main_provider(config=config, logger=logger)
    assert error is None
    response = await provider.chat([{"role": "user", "content": "hi"}])
    notice = response["extensions"]["native_vision_fallback"]
    assert notice["to_model"] == "vision_model"
    assert notice["from_model"] == "primary_chat_model"
    assert "视觉模型" in notice["notice"]
    assert provider.native_vision  # 视觉回退仍具备视觉能力
    # 创建失败记 error，能力不符记 warning，两者都说明发生了自动回退
    assert logger.error.called or logger.warning.called
    await provider.close()


def test_nonvision_main_does_not_create_fallback(monkeypatch):
    config = BotConfig()
    create = Mock(return_value=FakeProvider())
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert not isinstance(provider, NativeVisionFallbackProvider)
    create.assert_called_once_with("primary_chat_model")


def test_unavailable_vision_fallback_is_startup_error(monkeypatch):
    """视觉模型也不可用时，仍按启动错误处理（给出明确提示而不是崩溃）。"""
    config = BotConfig()
    config.models.primary_chat_model.native_vision = True
    create = Mock(side_effect=ValueError("missing key"))
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert provider is None
    assert "视觉模型不可用" in error


async def test_unavailable_nonvision_main_falls_back_to_vision_model(monkeypatch):
    """非视觉主模型创建失败时，自动回退到视觉模型而不是报错停机。"""
    config = BotConfig()

    def create(name):
        if name == "primary_chat_model":
            raise ValueError("missing key")
        return FakeProvider(native_vision=True)

    monkeypatch.setattr(_providers, "create_provider", create)
    logger = Mock()
    provider, error = _providers.build_main_provider(config=config, logger=logger)
    assert error is None
    assert not isinstance(provider, NativeVisionFallbackProvider)
    assert provider.native_vision
    assert logger.warning.called


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
    ).unwrap()
    document, _, _ = dataclass_to_toml(BotConfig, existing_data=data)
    parsed = tomlkit.parse(tomlkit.dumps(document)).unwrap()
    config = dict_to_dataclass(parsed, BotConfig)
    assert config.models.primary_chat_model.native_vision is True
    assert config.models.primary_chat_model.model_name == "deepseek-v4-flash-vision-exp"
    assert "main_agent_vision_fallback" not in tomlkit.dumps(document)


def test_native_vision_toml_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "test-key")
    path = tmp_path / "bot.toml"
    path.write_text(
        '[models.primary_chat_model]\n'
        'model_name = "deepseek-v4-flash-vision-exp"\n'
        'native_vision = true\n'
        '[agent_model]\nmain_agent = 2\n',
        encoding="utf-8",
    )
    registry = get_model_registry()
    saved = registry.items()
    try:
        config = Config.load(path, BotConfig)
        assert config.models.primary_chat_model.native_vision is True
        assert config.agent_model.main_agent == 2
        assert registry.get("primary_chat_model").native_vision
        reloaded = Config.load(path, BotConfig)
        assert reloaded.models.primary_chat_model.native_vision is True
        assert reloaded.agent_model.main_agent == 2
    finally:
        registry.clear()
        for _, model in saved:
            registry.register(model)
