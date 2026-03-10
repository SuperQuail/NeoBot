from __future__ import annotations

from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.types import State


def inject_skills(skills: SkillRegistry | None, state: State) -> State:
    """将匹配到的 skills 与已有 system prompt 合并为一条 XML 结构的 system message

    - 提取 messages 中已有的 system message（如有）
    - 匹配最后一条 user message 的 skills
    - 用 build_system_prompt 合并为统一的 <system> XML
    - 替换/插入到 messages 最前面，保证只有一条 system message
    """
    if not skills:
        return state

    messages = list(state.get("messages", []))
    user_msgs = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
    if not user_msgs:
        return state

    matched = skills.match(user_msgs[-1])
    if not matched:
        return state

    system_parts: list[str] = []
    rest: list[dict] = []
    for msg in messages:
        if msg.get("role") == "system":
            system_parts.append(msg.get("content", ""))
        else:
            rest.append(msg)

    prompt = SkillRegistry.build_system_prompt(
        instructions="\n\n".join(system_parts),
        skills=matched,
    )
    return {**state, "messages": [{"role": "system", "content": prompt}, *rest]}
