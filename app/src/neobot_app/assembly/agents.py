"""Agent model name resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import BotConfig


AGENT_MODEL_NAMES: dict[int, str] = {
    0: "primary_chat_model",
    1: "agent_model_1",
    2: "agent_model_2",
    3: "agent_model_3",
}


def resolve_agent_model_name(
    config: "BotConfig",
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
