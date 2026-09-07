"""Expose registered sub-agents to the main reply agent."""

from __future__ import annotations

from typing import Any

from neobot_app.skills.base import SkillModule

_DELEGATE_PARAMS = ("agent", "task", "tasks", "previous_response", "session_id")


class AgentDelegationSkill(SkillModule):
    def __init__(self, agent_registry: Any) -> None:
        self._registry = agent_registry

    @property
    def name(self) -> str:
        return "agents"

    @property
    def description(self) -> str:
        return "List available sub-agents and delegate complex tasks to them."

    @property
    def instructions(self) -> str:
        return (
            "Use agents__list to inspect available specialists. "
            "Use agents__delegate when a task clearly matches a specialist's description."
        )

    @staticmethod
    def _agent_prop(names: list[str], description: str) -> dict:
        # 模型枚举为空列表时部分提供商（OpenAI 系）会拒绝 schema，因此仅在非空时附带 enum
        prop: dict = {"type": "string", "description": description}
        if names:
            prop["enum"] = names
        return prop

    def get_tools(self) -> list[dict]:
        names = self._registry.names
        return [
            self._tool_def(
                "list",
                "List available sub-agents, or inspect one sub-agent's description.",
                {
                    "properties": {
                        "agent": self._agent_prop(
                            names, "Optional fully-qualified sub-agent name."
                        ),
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "delegate",
                "Delegate one task to a sub-agent, or several independent tasks in parallel.",
                {
                    "properties": {
                        "agent": self._agent_prop(
                            names, "Sub-agent to delegate the task to."
                        ),
                        "task": {"type": "string"},
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "agent": self._agent_prop(
                                        names, "Sub-agent to delegate the task to."
                                    ),
                                    "task": {"type": "string"},
                                    "session_id": {"type": "string"},
                                },
                                "required": ["agent", "task"],
                            },
                        },
                        "previous_response": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        values = dict(args)
        context = str(values.pop("_delegate_context", "") or "")
        values.pop("pipeline_key", None)
        values.pop("_numbering_mapping", None)
        if tool_name == "list":
            return self._registry.list_agents(values.get("agent"))
        if tool_name == "delegate":
            # 只透传 registry.delegate 认识的参数，模型幻想的多余键不进入 **kwargs
            kwargs = {key: values[key] for key in _DELEGATE_PARAMS if key in values}
            from neobot_app.agent_tools.invocation import CURRENT_INVOCATION
            invocation = CURRENT_INVOCATION.get()
            if invocation is not None:
                kwargs["execution_context"] = invocation.context
            return await self._registry.delegate(context=context, **kwargs)
        return f"Unknown agent tool: {tool_name}"
