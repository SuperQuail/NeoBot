"""Agent assembly helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_chat import AgentRegistry, create_provider
from neobot_chat.providers.base import Provider
from neobot_memory import ArchiveMemoryService

from neobot_app.agents import (
    build_archive_memory_agent,
    build_chat_interaction_agent,
    build_creator_agent,
    build_cross_chat_agent,
    build_image_parse_agent,
    build_problem_solver_agent,
    build_scheduled_task_agent,
    build_willingness_control_agent,
)
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.core import DATA_DIR

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.emoji.service import EmojiService
    from neobot_app.user_profiles import UserProfileService
    from neobot_app.willing.service import WillingService


AGENT_MODEL_NAMES: dict[int, str] = {
    0: "primary_chat_model",
    1: "agent_model_1",
    2: "agent_model_2",
    3: "agent_model_3",
}


def resolve_agent_model_name(
    config: BotConfig,
    agent_name: str,
    *,
    default_index: int,
) -> str:
    routing = getattr(config, "agent_model", None)
    raw_index = getattr(routing, agent_name, default_index)
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        index = default_index
    return AGENT_MODEL_NAMES.get(index, AGENT_MODEL_NAMES[default_index])


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
    provider_factory: Callable[..., Provider] | None = None,
    model_name: str = "primary_chat_model",
    logger: Logger | None = None,
    drawing_manager: Any = None,
    problem_solver_manager: Any = None,
    cross_chat_manager: Any = None,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
) -> AgentRegistry:
    registry = AgentRegistry()
    active_logger = logger or NullLogger()

    def factory(agent_name: str) -> Provider:
        if provider_factory is not None:
            try:
                return provider_factory(agent_name)
            except TypeError:
                return provider_factory()
        resolved_model_name = (
            model_name
            if model_name != "primary_chat_model"
            else resolve_agent_model_name(config, agent_name, default_index=1)
        )
        return create_provider(resolved_model_name)

    # Register creator agent
    creator_config = config.agent.creator
    if creator_config.enabled and adapter is not None and uow_factory is not None:
        try:
            provider = factory("creator")
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
                        markdown_dir=DATA_DIR / "markdown_images",
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
            provider = factory("memory")
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
            provider = factory("chat_interaction")
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
            provider = factory("willingness")
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

    # Register scheduled task agent
    scheduled_task_config = getattr(config, "scheduled_task", None)
    if (
        scheduled_task_config is not None
        and getattr(scheduled_task_config, "enabled", True)
        and uow_factory is not None
    ):
        try:
            provider = factory("scheduled_task")
        except Exception as exc:
            active_logger.warning(f"无法创建 scheduled task agent provider: {exc}")
        else:
            registry.register(
                "scheduled_task",
                build_scheduled_task_agent(
                    provider,
                    uow_factory=uow_factory,
                    config=scheduled_task_config,
                    logger=active_logger,
                ),
            )

    # Register problem_solver agent
    problem_solver_config = getattr(config.agent, "problem_solver", None)
    if (
        problem_solver_config is not None
        and getattr(problem_solver_config, "enabled", True)
    ):
        try:
            provider = factory("problem_solver")
        except Exception as exc:
            active_logger.warning(f"无法创建 problem solver agent provider: {exc}")
        else:
            try:
                web_search_cfg = getattr(config, "web_search", None)
                web_search_kwargs: dict = {}
                if web_search_cfg is not None and getattr(web_search_cfg, "enabled", True):
                    web_search_kwargs = {
                        "engines": ["bing", "duckduckgo"],
                        "max_rounds": getattr(web_search_cfg, "max_search_rounds", 5),
                        "preview_pages_limit": getattr(web_search_cfg, "preview_pages_limit", 30),
                        "variant_result_limit": getattr(web_search_cfg, "variant_result_limit", 6),
                    }
                registry.register(
                    "problem_solver",
                    build_problem_solver_agent(
                        provider,
                        config=problem_solver_config,
                        logger=active_logger,
                        manager=problem_solver_manager,
                        web_search_config=web_search_kwargs if web_search_kwargs else None,
                    ),
                )
            except Exception as exc:
                active_logger.warning(f"无法注册 problem solver agent: {exc}")

    # Register cross_chat agent
    cross_chat_config = getattr(config.agent, "cross_chat", None)
    if (
        cross_chat_config is not None
        and getattr(cross_chat_config, "enabled", True)
        and adapter is not None
    ):
        try:
            provider = factory("cross_chat")
        except Exception as exc:
            active_logger.warning(f"无法创建 cross_chat agent provider: {exc}")
        else:
            try:
                registry.register(
                    "cross_chat",
                    build_cross_chat_agent(
                        provider,
                        config=cross_chat_config,
                        logger=active_logger,
                        manager=cross_chat_manager,
                        adapter=adapter,
                        group_message_queue=group_message_queue,
                        friend_message_queue=friend_message_queue,
                        bot_config=config,
                    ),
                )
            except Exception as exc:
                active_logger.warning(f"无法注册 cross_chat agent: {exc}")

    return registry
