from __future__ import annotations

from typing import Callable

from neobot_chat.skills.inject import inject_skills
from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.types import State


def skill_node(skills: SkillRegistry) -> Callable[[State], State]:
    """创建一个 Graph 内置节点，自动匹配 skills 并注入 system prompt

    用法::

        graph.add_node("skills", skill_node(registry))
        graph.add_edge("skills", "agent")
        graph.set_entry_point("skills")
    """

    async def _node(state: State) -> State:
        return inject_skills(skills, state)

    return _node
