"""Agent assembly helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_chat import AgentRegistry, create_provider
from neobot_chat.providers.base import Provider
from neobot_memory import ArchiveMemoryService

from neobot_app.agents import (
    build_archive_memory_agent,
    build_chat_interaction_agent,
    build_creator_agent,
    build_image_parse_agent,
    build_willingness_control_agent,
)
from neobot_app.config.schemas.bot import BotConfig

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.emoji.service import EmojiService
    from neobot_app.user_profiles import UserProfileService
    from neobot_app.willing.service import WillingService


def build_agent_registry(
    *,
    config: BotConfig,
    archive_memory_service: ArchiveMemoryService | None = None,
    uow_factory: UnitOfWorkFactory | None = None,
    adapter: "OneBotAdapter | None" = None,
    emoji_service: "EmojiService | None" = None,
    profile_service: "UserProfileService | None" = None,
    vision_provider: "Provider | None" = None,
    willing_service: "WillingService | None" = None,
    provider_factory: Callable[[], Provider] | None = None,
    model_name: str = "primary_chat_model",
    logger: Logger | None = None,
    drawing_manager: Any = None,
) -> AgentRegistry:
    registry = AgentRegistry()
    active_logger = logger or NullLogger()

    factory = provider_factory or (lambda: create_provider(model_name))

    # Register creator agent
    creator_config = config.agent.creator
    if creator_config.enabled and adapter is not None and uow_factory is not None:
        try:
            provider = factory()
        except Exception as exc:
            active_logger.warning(f"无法创建 creator agent provider: {exc}")
        else:
            try:
                registry.register(
                    "creator",
                    build_creator_agent(
                        provider,
                        uow_factory=uow_factory,
                        adapter=adapter,
                        config=creator_config,
                        emoji_service=emoji_service,
                        vision_provider=vision_provider,
                        logger=active_logger,
                        drawing_manager=drawing_manager,
                    ),
                )
            except Exception as exc:
                active_logger.warning(f"无法注册 creator agent: {exc}")

    # Register memory agent
    archive_config = config.agent.memory.archive
    favorability_config = config.agent.memory.favorability
    if archive_memory_service is not None:
        try:
            provider = factory()
        except Exception as exc:
            active_logger.warning(f"无法创建 memory agent provider: {exc}")
        else:
            registry.register(
                "memory",
                build_archive_memory_agent(
                    provider,
                    archive_memory_service,
                    config=archive_config,
                    favorability_config=favorability_config,
                    profile_service=profile_service,
                    adapter=adapter,
                    image_parse_provider=vision_provider,
                    logger=active_logger,
                ),
            )

    # Register chat_interaction agent
    if adapter is not None:
        try:
            provider = factory()
        except Exception as exc:
            active_logger.warning(f"无法创建 chat interaction agent provider: {exc}")
        else:
            registry.register(
                "chat_interaction",
                build_chat_interaction_agent(
                    provider,
                    adapter=adapter,
                    emoji_service=emoji_service,
                    profile_service=profile_service,
                    logger=active_logger,
                    forward_display_threshold=getattr(
                        config.chat, "forward_message_display_threshold", 50,
                    ),
                    forward_max_nesting=getattr(
                        config.chat, "forward_message_max_nesting", 10,
                    ),
                ),
            )

    # Register image_parse agent with the configured vision model provider.
    if vision_provider is not None:
        try:
            registry.register(
                "image_parse",
                build_image_parse_agent(
                    vision_provider,
                    adapter=adapter,
                    logger=active_logger,
                ),
            )
        except Exception as exc:
            active_logger.warning(f"无法注册 image_parse agent: {exc}")

    # Register willingness control agent
    willingness_config = config.agent.willingness
    if willingness_config.enabled and willing_service is not None:
        try:
            provider = factory()
        except Exception as exc:
            active_logger.warning(f"无法创建 willingness control agent provider: {exc}")
        else:
            registry.register(
                "willingness",
                build_willingness_control_agent(
                    provider,
                    willing_service=willing_service,
                    logger=active_logger,
                ),
            )

    return registry
