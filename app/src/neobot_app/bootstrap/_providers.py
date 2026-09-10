"""AI Provider 创建"""

from __future__ import annotations

from typing import Any

from neobot_chat import create_provider
from neobot_chat.providers.native_vision import NativeVisionFallbackProvider
from neobot_app.assembly.agents import resolve_agent_model_name
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema


VISION_MODEL_NAME = "vision_model"


def resolve_vision_model_name(config: BotConfigSchema) -> str:
    """视觉模型引用的 key（找不到时回退到旧角色名）。"""
    assignments = getattr(getattr(config, "models", None), "assignments", None)
    key = str(getattr(assignments, "vision_model", "") or "").strip() if assignments else ""
    models = getattr(config, "models", None)
    if key and models is not None and hasattr(models, "get") and models.get(key) is not None:
        return key
    return VISION_MODEL_NAME


def build_main_provider(
    *,
    config: BotConfigSchema,
    logger: Any,
    vision_provider: Any = None,
) -> tuple[Any, str | None]:
    """创建主对话 provider。返回 (provider, error_message)。

    主模型不可用（创建失败）时自动回退到视觉模型（vision_model）：视觉模型本身
    具备完整对话能力，保证 Bot 仍能正常回复，不需要用户再手选回退模型。
    主模型声明原生视觉但无法处理图片时，同样自动切换到视觉模型并保留图片。

    **返回契约**：``provider is None`` 时 ``error_message`` 必须非空。
    否则调用方（回复编排器、面板状态）拿到 None 却没有任何可展示的原因，
    「能启动但不会回复」就变成了无法定位的静默故障。
    """
    main_model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    vision_model_name = resolve_vision_model_name(config)
    provider = None
    main_config = (
        config.models.get(main_model_name)
        if hasattr(config.models, "get")
        else getattr(config.models, main_model_name, None)
    )
    if getattr(main_config, "native_vision", False):
        startup_reason = None
        try:
            provider = create_provider(main_model_name)
        except Exception as exc:
            logger.error(f"无法创建主对话原生视觉 provider({main_model_name}): {exc}")
            startup_reason = "配置的原生视觉 provider 无法创建"
        if provider is not None and not getattr(provider, "native_vision", False):
            startup_reason = "配置启用了原生视觉，但实际 provider 未暴露图片发送能力"
        fallback = vision_provider or build_vision_provider(
            logger=logger, model_name=vision_model_name
        )
        if fallback is None:
            error = "视觉模型不可用，无法建立原生视觉回退；请检查 vision_model 分配与配置"
            logger.error(error)
            return None, error
        provider = NativeVisionFallbackProvider(
            provider, fallback, logger=logger,
            primary_name=main_model_name, fallback_name=vision_model_name,
            startup_reason=startup_reason, strip_images=False,
        )
    else:
        try:
            provider = create_provider(main_model_name)
        except Exception as exc:
            logger.error(f"无法创建主对话 chat provider({main_model_name}): {exc}")

    if provider is None:
        # 主模型不可用：自动回退到视觉模型（而不是让用户手选另一个模型）
        fallback = vision_provider or build_vision_provider(
            logger=logger, model_name=vision_model_name
        )
        if fallback is not None:
            logger.warning(f"主对话模型不可用，已自动回退到视觉模型({vision_model_name})")
            return fallback, None

    if provider is None:
        # 主模型与视觉回退都不可用：必须给出可展示的原因（不能返回 (None, None)）。
        error_message = (
            f"当前主回复模型不可用（{main_model_name}），请检查 [models] 配置与对应平台的 API Key"
        )
        logger.error(error_message)
        return None, error_message

    return provider, None


def build_vision_provider(*, logger: Any, model_name: str = VISION_MODEL_NAME) -> Any:
    """创建视觉模型 provider（失败返回 None）。"""
    try:
        return create_provider(model_name)
    except Exception as exc:
        logger.warning(f"无法创建视觉模型 provider({model_name}): {exc}")
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
