from __future__ import annotations

import asyncio
from typing import Protocol

from neobot_chat.types import State


class AgentProtocol(Protocol):
    """子 Agent 必须实现的接口"""

    description: str
    custom_tools: list[dict]

    async def invoke(self, state: State) -> State: ...


class AgentRegistry:
    """子 Agent 注册表"""

    def __init__(self):
        self._agents: dict[str, AgentProtocol] = {}

    def register(self, name: str, agent: AgentProtocol) -> None:
        self._agents[name] = agent

    @property
    def names(self) -> list[str]:
        return list(self._agents)

    def __len__(self) -> int:
        return len(self._agents)

    def __bool__(self) -> bool:
        return bool(self._agents)

    def list_agents(self, name: str | None = None) -> str:
        if not self._agents:
            return "No agents available"

        if name is None:
            lines = [f"- {n}: {a.description}" for n, a in self._agents.items()]
            return "Available agents:\n" + "\n".join(lines)

        agent = self._agents.get(name)
        if not agent:
            return f"Agent '{name}' not found"

        header = f"Agent {name}: {agent.description}"
        if not agent.custom_tools:
            return header

        lines = [
            f"- {t['function']['name']}: {t['function'].get('description', '')}"
            for t in agent.custom_tools
        ]
        return f"{header}\nTools:\n" + "\n".join(lines)

    async def delegate(
            self,
            agent: str | None = None,
            task: str | None = None,
            tasks: list[dict] | None = None,
    ) -> str:
        if tasks:
            coros = [
                self.delegate(agent=t["agent"], task=t["task"]) for t in tasks
            ]
            results = await asyncio.gather(*coros)
            return "\n\n".join(
                f"{t['agent']}: {r}" for t, r in zip(tasks, results)
            )

        if not agent or not task:
            return "Missing agent or task parameter"

        agent_obj = self._agents.get(agent)
        if not agent_obj:
            return f"Agent '{agent}' not found"

        result = await agent_obj.invoke(
            {"messages": [{"role": "user", "content": task}]}
        )
        return result["messages"][-1]["content"]
