from __future__ import annotations

import asyncio

from neobot_chat.schema.protocol import AgentLike


class AgentRegistry:
    """子 Agent 注册表"""

    def __init__(self):
        self._agents: dict[str, AgentLike] = {}
        self._sessions: dict[str, list[dict]] = {}

    def register(self, name: str, agent: AgentLike) -> None:
        self._agents[name] = agent

    @property
    def names(self) -> list[str]:
        return list(self._agents)

    def snapshot(self) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "description": getattr(agent, "description", ""),
            }
            for name, agent in self._agents.items()
        ]

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

        return f"Agent {name}: {agent.description}"

    async def delegate(
        self,
        agent: str | None = None,
        task: str | None = None,
        tasks: list[dict] | None = None,
        previous_response: str | None = None,
        session_id: str | None = None,
        context: str | None = None,
    ) -> str:
        if tasks:
            coros = [
                self.delegate(
                    agent=t["agent"],
                    task=t["task"],
                    previous_response=t.get("previous_response"),
                    session_id=t.get("session_id"),
                    context=context,
                )
                for t in tasks
            ]
            results = await asyncio.gather(*coros)
            return "\n\n".join(f"{t['agent']}: {r}" for t, r in zip(tasks, results))

        if not agent or not task:
            return "Missing agent or task parameter"

        agent_obj = self._agents.get(agent)
        if not agent_obj:
            return f"Agent '{agent}' not found"

        session_key = self._session_key(agent, session_id)
        messages = list(self._sessions.get(session_key, [])) if session_key else []
        if previous_response and previous_response.strip():
            messages.append({"role": "assistant", "content": previous_response.strip()})
        messages.append({"role": "user", "content": task})

        result = await agent_obj.invoke(
            {
                "messages": messages,
                "_delegate_context": context.strip() if context else "",
            }
        )
        content = result["messages"][-1].get("content")
        result_text = content if isinstance(content, str) else str(content)
        if session_key:
            self._sessions[session_key] = self._trim_session(
                [
                    *messages,
                    {"role": "assistant", "content": result_text},
                ]
            )
        return result_text

    @staticmethod
    def _session_key(agent: str, session_id: str | None) -> str | None:
        session = str(session_id or "").strip()
        if not session:
            return None
        return f"{agent}:{session}"

    @staticmethod
    def _trim_session(messages: list[dict], *, max_messages: int = 16) -> list[dict]:
        system_messages = [message for message in messages if message.get("role") == "system"]
        rest = [message for message in messages if message.get("role") != "system"]
        return [*system_messages[:1], *rest[-max_messages:]]

    async def close(self) -> None:
        if not self._agents:
            return
        await asyncio.gather(
            *(agent.close() for agent in self._agents.values()),
            return_exceptions=True,
        )
