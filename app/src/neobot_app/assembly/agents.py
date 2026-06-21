"""Agent model name resolution helpers and peer descriptions."""

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

AGENT_SHORT_DESCRIPTIONS: dict[str, str] = {
    "problem_solver": "复杂问题解题（数学、编程、科学推理等高难度深度推理）",
    "main_agent": "主对话智能体（日常聊天、问答、搜索、任务协调）",
}


def build_peer_descriptions(agent_name: str) -> str:
    """生成除了自身之外的其他 agent 的简短描述列表。"""
    lines: list[str] = []
    for name, desc in AGENT_SHORT_DESCRIPTIONS.items():
        if name == agent_name:
            continue
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


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
