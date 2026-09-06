"""AI Provider 创建"""

from __future__ import annotations

from typing import Any

from neobot_chat import create_provider
from neobot_chat.providers.native_vision import NativeVisionFallbackProvider
from neobot_app.assembly.agents import AGENT_MODEL_NAMES, resolve_agent_model_name
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema


def build_main_provider(
    *,
    config: BotConfigSchema,
    logger: Any,
) -> tuple[Any, str | None]:
    """创建主对话 provider。返回 (provider, error_message)。"""
    main_model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    provider = None
    main_config = getattr(config.models, main_model_name)
    if getattr(main_config, "native_vision", False):
        # Resolve strictly: an invalid fallback must not silently choose another model.
        index = getattr(config.agent_model, "main_agent_vision_fallback", 1)
        fallback_name = AGENT_MODEL_NAMES.get(index) if type(index) is int else None
        if fallback_name is None or fallback_name == main_model_name:
            error = "原生视觉回退配置无效：main_agent_vision_fallback 必须为不同于主模型的 0-3 编号"
            logger.error(error)
            return None, error
        if getattr(getattr(config.models, fallback_name), "native_vision", False):
            error = "原生视觉回退配置无效：回退模型必须设置 native_vision=false"
            logger.error(error)
            return None, error
        try:
            fallback = create_provider(fallback_name)
        except Exception as exc:
            error = f"无法创建原生视觉非视觉回退 provider({fallback_name}): {exc}"
            logger.error(error)
            return None, error
        startup_reason = None
        try:
            provider = create_provider(main_model_name)
        except Exception as exc:
            logger.error(f"无法创建主对话原生视觉 provider({main_model_name}): {exc}")
            startup_reason = "配置的原生视觉 provider 无法创建"
        if provider is not None and not getattr(provider, "native_vision", False):
            startup_reason = "配置启用了原生视觉，但实际 provider 未暴露图片发送能力"
        provider = NativeVisionFallbackProvider(
            provider, fallback, logger=logger,
            primary_name=main_model_name, fallback_name=fallback_name,
            startup_reason=startup_reason,
        )
    else:
        try:
            provider = create_provider(main_model_name)
        except Exception as exc:
            logger.error(f"无法创建主对话 chat provider({main_model_name}): {exc}")

    error_message = None
    if provider is None:
        error_message = "当前主回复模型不可用，请检查模型配置与 API Key"
        logger.error(error_message)

    return provider, error_message


def build_vision_provider(*, logger: Any) -> Any:
    """创建视觉模型 provider（失败返回 None）。"""
    try:
        return create_provider("vision_model")
    except Exception as exc:
        logger.warning(f"无法创建视觉模型 provider: {exc}")
        return None


def build_optional_agent_provider(
    *,
    config: BotConfigSchema,
    agent_name: str,
    fallback_provider: Any,
    logger: Any,
) -> Any:
    """创建可选 Agent 的 provider，失败时回退到 fallback。"""
    model_name = resolve_agent_model_name(config, agent_name, default_index=1)
    try:
        return create_provider(model_name)
    except Exception as exc:
        logger.warning(
            f"无法创建 {agent_name} provider({model_name})，回退到主回复 provider: {exc}"
        )
        return fallback_provider
