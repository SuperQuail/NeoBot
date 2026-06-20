"""AI Provider 创建"""

from __future__ import annotations

from typing import Any

from neobot_chat import create_provider
from neobot_app.assembly.agents import resolve_agent_model_name
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema


def build_main_provider(
    *,
    config: BotConfigSchema,
    logger: Any,
) -> tuple[Any, str | None]:
    """创建主对话 provider。返回 (provider, error_message)。"""
    main_model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    provider = None
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
