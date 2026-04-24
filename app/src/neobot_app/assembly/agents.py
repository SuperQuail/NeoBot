"""Agent assembly helpers."""

from __future__ import annotations

from collections.abc import Callable

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_chat import AgentRegistry, create_provider
from neobot_chat.providers.base import Provider
from neobot_memory import ArchiveMemoryService

from neobot_app.agents import build_archive_memory_agent
from neobot_app.config.schemas.bot import BotConfig


def build_agent_registry(
    *,
    config: BotConfig,
    archive_memory_service: ArchiveMemoryService | None = None,
    provider_factory: Callable[[], Provider] | None = None,
    model_name: str = "primary_chat_model",
    logger: Logger | None = None,
) -> AgentRegistry:
    registry = AgentRegistry()
    active_logger = logger or NullLogger()

    archive_config = config.agent.memory.archive
    if archive_memory_service is None:
        return registry

    factory = provider_factory or (lambda: create_provider(model_name))
    try:
        provider = factory()
    except Exception as exc:
        active_logger.warning(f"无法创建 archive memory agent provider: {exc}")
        return registry

    registry.register(
        "archive_memory",
        build_archive_memory_agent(
            provider,
            archive_memory_service,
            config=archive_config,
            logger=active_logger,
        ),
    )
    return registry
