"""启动时配置缺失集中提示，真实模型初始化异常仍保留堆栈。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from neobot_app.bootstrap import _providers
from neobot_app.config.availability import ModelAvailabilityPolicy
from neobot_app.config.loader import manager
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.config.schemas.env import EnvConfig
from neobot_chat.schema.exceptions import ValidationError


def _missing_platform_keys(monkeypatch) -> Mock:
    logger = Mock()
    monkeypatch.setattr(manager, "logger", logger)
    monkeypatch.setattr(
        EnvConfig,
        "get_api_platform_config",
        lambda _provider: SimpleNamespace(url="https://fixture.invalid", api_key=""),
    )
    return logger


def test_same_missing_key_has_one_warning_and_full_debug_findings(monkeypatch) -> None:
    logger = _missing_platform_keys(monkeypatch)

    manager.Config.register_models(BotConfig())

    logger.warning.assert_called_once()
    summary = logger.warning.call_args
    assert summary.kwargs["event"] == "config.models_degraded"
    assert summary.kwargs["missing_settings"] == ["平台 DeepSeek_APIKey 配置"]
    assert summary.kwargs["available_count"] == 0
    assert summary.kwargs["unavailable_count"] == 4
    details = "\n".join(
        call.args[0] for call in logger.debug.call_args_list if call.kwargs.get("event") == "config.model_unavailable"
    )
    assert "primary_chat_model" in details
    assert "agent_model_1" in details
    assert "vision_model" in details
    logger.error.assert_not_called()
    logger.exception.assert_not_called()


def test_strict_missing_configuration_still_raises_without_software_error_log(monkeypatch) -> None:
    logger = _missing_platform_keys(monkeypatch)

    with pytest.raises(manager.ConfigLoadError, match="DeepSeek_APIKey"):
        manager.Config.register_models(BotConfig(), availability_policy=ModelAvailabilityPolicy())

    assert logger.warning.call_args.kwargs["event"] == "config.model_validation_failed"
    logger.error.assert_not_called()
    logger.exception.assert_not_called()


def test_unavailable_providers_have_one_actionable_warning_without_error(monkeypatch) -> None:
    logger = Mock()
    create = Mock(side_effect=ValidationError("Model is not registered"))
    monkeypatch.setattr(_providers, "create_provider", create)

    provider, error = _providers.build_main_provider(config=BotConfig(), logger=logger)

    assert provider is None
    assert "视觉模型不可用" in error
    logger.warning.assert_called_once()
    assert logger.warning.call_args.kwargs["event"] == "provider.main_unavailable"
    logger.error.assert_not_called()
    logger.exception.assert_not_called()
    assert create.call_count == 2


def test_explicit_unavailable_vision_provider_is_not_created_again(monkeypatch) -> None:
    create = Mock(side_effect=ValidationError("Model is not registered"))
    monkeypatch.setattr(_providers, "create_provider", create)

    provider, error = _providers.build_main_provider(config=BotConfig(), logger=Mock(), vision_provider=None)

    assert provider is None and error
    create.assert_called_once_with("deepseek-flash")


def test_optional_missing_model_uses_fallback_without_repeated_warning(monkeypatch) -> None:
    monkeypatch.setattr(_providers, "create_provider", Mock(side_effect=ValidationError("Model is not registered")))
    logger = Mock()
    fallback = object()

    provider = _providers.build_optional_agent_provider(
        config=BotConfig(),
        agent_name="self_heal_agent",
        fallback_provider=fallback,
        logger=logger,
    )

    assert provider is fallback
    logger.warning.assert_not_called()
    logger.error.assert_not_called()
    logger.exception.assert_not_called()
    assert logger.debug.called


def test_unexpected_provider_error_keeps_exception_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(_providers, "create_provider", Mock(side_effect=RuntimeError("fixture constructor failed")))
    logger = Mock()

    assert _providers.build_vision_provider(logger=logger) is None

    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["error"] == "fixture constructor failed"
