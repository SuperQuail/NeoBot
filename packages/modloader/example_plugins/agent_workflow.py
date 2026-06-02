"""Example plugin for delegated sub-agents."""

from typing import Any

from neobot_chat import State, Workflow
from neobot_modloader import AgentRequest, Plugin

plugin = Plugin(
    "agent_workflow",
    description="Sub-agent examples for the Plugin API",
)


@plugin.agent("echo", description="Echo delegated tasks")
async def echo(task: str, request: AgentRequest) -> str:
    return f"{request.delegate_context}: {task}" if request.delegate_context else task


async def parse_task(state: State) -> State:
    messages = list(state.get("messages", []))
    task = str(messages[-1].get("content", "")) if messages else ""
    return {**state, "_task": task}


async def finish_task(state: State) -> State:
    messages: list[dict[str, Any]] = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": f"workflow done: {state.get('_task', '')}"})
    return {**state, "messages": messages}


@plugin.agent("workflow", description="Handle delegated tasks with a Workflow", factory=True)
def build_workflow() -> Workflow:
    return Workflow().add_step(parse_task).add_step(finish_task)
