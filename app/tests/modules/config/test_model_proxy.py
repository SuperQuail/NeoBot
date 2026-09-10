"""模型级「使用系统代理」开关：schema 默认值、注册传递与 Provider 接线。"""

from __future__ import annotations

from neobot_chat import (
    ModelPricing,
    ModelSettings,
    RegisteredModel,
    get_model_registry,
)

from neobot_app.config.schemas.bot import BotConfig, ModelDefinition


def test_model_definition_defaults_to_direct_connection() -> None:
    definition = ModelDefinition(key="demo")

    assert definition.use_system_proxy is False


def test_default_library_models_are_direct() -> None:
    config = BotConfig()

    assert all(item.use_system_proxy is False for item in config.models.registry)


def test_registered_model_threads_flag_into_provider() -> None:
    direct = RegisteredModel(
        name="direct",
        description="",
        provider_name="DeepSeek",
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        settings=ModelSettings(),
        pricing=ModelPricing(),
    )
    proxied = RegisteredModel(
        name="proxied",
        description="",
        provider_name="DeepSeek",
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        settings=ModelSettings(),
        pricing=ModelPricing(),
        use_system_proxy=True,
    )

    direct_provider = direct.create_provider()
    proxied_provider = proxied.create_provider()

    assert direct_provider.use_system_proxy is False
    assert direct_provider.client.trust_env is False
    assert proxied_provider.use_system_proxy is True
    assert proxied_provider.client.trust_env is True


def test_register_models_passes_proxy_flag(monkeypatch) -> None:
    from neobot_app.config.loader.manager import Config

    config = BotConfig()
    entry = config.models.get("deepseek-v4-pro")
    assert entry is not None
    entry.use_system_proxy = True
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "sk-test")

    Config.register_models(config)

    registered = get_model_registry().get("deepseek-v4-pro")
    assert registered.use_system_proxy is True
    assert registered.create_provider().use_system_proxy is True
