"""Agent 模型名称解析辅助函数与同伴描述。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import BotConfig


#: Agent 模型编号 -> 调用方角色名（角色只引用模型库中的 key）
AGENT_ROLE_NAMES: dict[int, str] = {
    0: "primary_chat_model",
    1: "agent_model_1",
    2: "agent_model_2",
    3: "agent_model_3",
}

#: 兼容旧名称
AGENT_MODEL_NAMES = AGENT_ROLE_NAMES

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
    """返回该 Agent 引用的模型 key（模型库中定义的 key）。

    找不到分配或 key 不在模型库时回退到角色名，兼容尚未迁移的旧配置。
    """
    routing = getattr(config, "agent_model", None)
    raw_index = getattr(routing, agent_name, default_index)
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        index = default_index
    role = AGENT_ROLE_NAMES.get(index, AGENT_ROLE_NAMES[default_index])

    models = getattr(config, "models", None)
    assignments = getattr(models, "assignments", None)
    if assignments is not None and hasattr(models, "get"):
        key = str(getattr(assignments, role, "") or "").strip()
        if key and models.get(key) is not None:
            return key
    return role
