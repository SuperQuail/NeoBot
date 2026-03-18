from __future__ import annotations

from neobot_chat.schema.protocol import StatePreprocessor
from neobot_chat.schema.types import Message, State
from neobot_chat.skills.registry import SkillRegistry


def inject_skills(skills: SkillRegistry | None, state: State) -> State:
    """匹配最后一条 user message 对应的 skills，并挂到 state 上。"""
    if not skills:
        return state

    messages: list[Message] = list(state.get("messages", []))
    user_msgs = [
        content
        for m in messages
        if m.get("role") == "user"
        for content in [m.get("content")]
        if isinstance(content, str) and content
    ]
    if not user_msgs:
        return state

    matched = skills.match(user_msgs[-1])
    next_state = dict(state)
    if matched:
        next_state["_matched_skills"] = matched
    else:
        next_state.pop("_matched_skills", None)
    return next_state


def build_skill_preprocessor(skills: SkillRegistry | None) -> StatePreprocessor | None:
    """将 SkillRegistry 包装为标准预处理器。"""

    if not skills:
        return None
    return lambda state: inject_skills(skills, state)
