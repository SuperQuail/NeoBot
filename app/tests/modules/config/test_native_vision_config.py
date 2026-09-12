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

PRIMARY_KEY = "deepseek-v4-pro"
VISION_KEY = "qwen3-vl-8b"


class FakeProvider:
    def __init__(self, native_vision=False):
        self.native_vision = native_vision
        self.model = "vision" if native_vision else "text"

    async def chat(self, messages, tools=None):
        return {"role": "assistant", "content": "ok"}

    async def close(self):
        pass


def _library_entry(config: BotConfig, key: str):
    definition = config.models.get(key)
    assert definition is not None
    return definition


def test_native_vision_defaults():
    config = BotConfig()
    # 数据类层面的默认值保持 False：旧配置与外部脚本不受影响
    assert ModelRegistration().native_vision is False
    # 但默认模型库里的对话模型已声明原生视觉（deepseek-flash）
    assert _library_entry(config, PRIMARY_KEY).native_vision is True
    # 图像识别模型无需配置 native_vision：按 model_type=vision 自动视为原生视觉
    assert _library_entry(config, VISION_KEY).native_vision is True
    assert config.models.assignments.primary_chat_model == PRIMARY_KEY
    assert config.models.assignments.vision_model == VISION_KEY
    assert config.chat.native_vision_default_image_count == 4
    # 回退目标固定为视觉模型，不再需要用户手选回退模型编号
    assert "main_agent_vision_fallback" not in {
        f.name for f in dataclasses.fields(config.agent_model)
    }


def test_config_registration_passes_native_vision(monkeypatch):
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "test-key")
    config = BotConfig()
    primary = _library_entry(config, PRIMARY_KEY)
    primary.native_vision = True
    primary.model_name = "deepseek-v4-flash-vision-exp"
    # 默认全部为原生视觉，这里显式关掉一个以验证 False 也能正确透传
    _library_entry(config, "deepseek-v4-flash-max").native_vision = False
    registry = get_model_registry()
    saved = registry.items()
    try:
        Config.register_models(config)
        main = registry.get(PRIMARY_KEY)
        assert main.native_vision
        assert main.create_provider().native_vision
        assert not registry.get("deepseek-v4-flash-max").native_vision
    finally:
        registry.clear()
        for _, model in saved:
            registry.register(model)


async def test_bootstrap_wraps_main_with_vision_model_fallback(monkeypatch):
    """主模型声明原生视觉时，回退路由固定为视觉模型（按分配 key 解析）。"""
    config = BotConfig()
    config.agent_model.main_agent = 2
    _library_entry(config, "deepseek-v4-flash-high").native_vision = True
    created = []

    def create(name):
        created.append(name)
        return FakeProvider(native_vision=True)

    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert isinstance(provider, NativeVisionFallbackProvider)
    assert provider.native_vision
    assert created == ["deepseek-v4-flash-high", VISION_KEY]
    await provider.close()


@pytest.mark.parametrize("failure", ["creation", "capability"])
async def test_unavailable_primary_falls_back_to_vision_model(monkeypatch, failure):
    """主模型不可用（创建失败或无视觉能力）时自动切换到视觉模型，图片照常发送。"""
    config = BotConfig()
    _library_entry(config, PRIMARY_KEY).native_vision = True

    def create(name):
        if name == PRIMARY_KEY and failure == "creation":
            raise ValueError("unavailable")
        if name == VISION_KEY:
            return FakeProvider(native_vision=True)
        return FakeProvider(native_vision=False)

    monkeypatch.setattr(_providers, "create_provider", create)
    logger = Mock()
    provider, error = _providers.build_main_provider(config=config, logger=logger)
    assert error is None
    response = await provider.chat([{"role": "user", "content": "hi"}])
    notice = response["extensions"]["native_vision_fallback"]
    assert notice["to_model"] == VISION_KEY
    assert notice["from_model"] == PRIMARY_KEY
    assert "视觉模型" in notice["notice"]
    assert provider.native_vision  # 视觉回退仍具备视觉能力
    # 创建失败记 error，能力不符记 warning，两者都说明发生了自动回退
    assert logger.error.called or logger.warning.called
    await provider.close()


def test_nonvision_main_does_not_create_fallback(monkeypatch):
    config = BotConfig()
    # 默认主模型已声明原生视觉；这里显式关掉以覆盖"非视觉主模型"分支
    _library_entry(config, PRIMARY_KEY).native_vision = False
    create = Mock(return_value=FakeProvider())
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert error is None
    assert not isinstance(provider, NativeVisionFallbackProvider)
    create.assert_called_once_with(PRIMARY_KEY)


def test_unavailable_vision_fallback_is_startup_error(monkeypatch):
    """视觉模型也不可用时，仍按启动错误处理（给出明确提示而不是崩溃）。"""
    config = BotConfig()
    _library_entry(config, PRIMARY_KEY).native_vision = True
    create = Mock(side_effect=ValueError("missing key"))
    monkeypatch.setattr(_providers, "create_provider", create)
    provider, error = _providers.build_main_provider(config=config, logger=Mock())
    assert provider is None
    assert "视觉模型不可用" in error


async def test_unavailable_nonvision_main_falls_back_to_vision_model(monkeypatch):
    """非视觉主模型创建失败时，自动回退到视觉模型而不是报错停机。"""
    config = BotConfig()
    _library_entry(config, PRIMARY_KEY).native_vision = False

    def create(name):
        if name == PRIMARY_KEY:
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
        '[[models.registry]]\n'
        'key = "deepseek-v4-pro"\n'
        'model_name = "deepseek-v4-flash-vision-exp"\n'
        'native_vision = true\n'
    ).unwrap()
    document, _, _ = dataclass_to_toml(BotConfig, existing_data=data)
    parsed = tomlkit.parse(tomlkit.dumps(document)).unwrap()
    config = dict_to_dataclass(parsed, BotConfig)
    entry = _library_entry(config, PRIMARY_KEY)
    assert entry.native_vision is True
    assert entry.model_name == "deepseek-v4-flash-vision-exp"
    assert "main_agent_vision_fallback" not in tomlkit.dumps(document)


def test_native_vision_toml_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "test-key")
    path = tmp_path / "bot.toml"
    # 只保留一个模型库条目时，所有角色都指向它（避免引用不存在的 key）
    path.write_text(
        '[[models.registry]]\n'
        'key = "deepseek-v4-pro"\n'
        'model_name = "deepseek-v4-flash-vision-exp"\n'
        'native_vision = true\n'
        '\n'
        '[models.assignments]\n'
        'primary_chat_model = "deepseek-v4-pro"\n'
        'agent_model_1 = "deepseek-v4-pro"\n'
        'agent_model_2 = "deepseek-v4-pro"\n'
        'agent_model_3 = "deepseek-v4-pro"\n'
        'vision_model = "deepseek-v4-pro"\n'
        'tts_model = "deepseek-v4-pro"\n'
        'creator_image_models = []\n'
        '\n'
        '[agent_model]\nmain_agent = 2\n',
        encoding="utf-8",
    )
    registry = get_model_registry()
    saved = registry.items()
    try:
        config = Config.load(path, BotConfig)
        assert _library_entry(config, PRIMARY_KEY).native_vision is True
        assert config.agent_model.main_agent == 2
        assert registry.get(PRIMARY_KEY).native_vision
        reloaded = Config.load(path, BotConfig)
        assert _library_entry(reloaded, PRIMARY_KEY).native_vision is True
        assert reloaded.agent_model.main_agent == 2
    finally:
        registry.clear()
        for _, model in saved:
            registry.register(model)
