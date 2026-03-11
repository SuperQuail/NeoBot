from __future__ import annotations

from pathlib import Path

from neobot_chat.runtime.agent import Agent
from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import StatePreprocessor, ToolExecutor
from neobot_chat.providers.base import Provider
from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.tools import AgentRegistry, BuiltinTools, CompositeToolExecutor
from neobot_chat.schema.types import OnEvent, ToolDefinition


class EmptyToolExecutor(ToolExecutor):
    """不提供任何工具的执行器。"""

    def definitions(self) -> list[ToolDefinition]:
        return []

    async def execute(self, name: str, args: dict) -> str:
        raise ToolError(f"Unknown tool: {name}")

    async def close(self) -> None:
        return None


def create_basic_agent(
    provider: Provider,
    *,
    preprocessor: StatePreprocessor | None = None,
    system_prompt: str | None = None,
    max_iterations: int = 10,
    on_event: OnEvent | None = None,
    description: str = "",
) -> Agent:
    """创建一个不带任何工具的基础聊天 Agent。"""

    return Agent(
        provider=provider,
        tool_executor=EmptyToolExecutor(),
        preprocessor=preprocessor,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        on_event=on_event,
        description=description,
    )


def create_tool_agent(
    provider: Provider,
    *,
    executors: list[ToolExecutor] | None = None,
    tools: list[ToolDefinition] | None = None,
    preprocessor: StatePreprocessor | None = None,
    agent_registry: AgentRegistry | None = None,
    skills: SkillRegistry | None = None,
    description: str = "",
    cwd: str | Path | None = None,
    max_iterations: int = 10,
    command_timeout: int = 30,
    allowed_commands: list[str] | None = None,
    system_prompt: str | None = None,
    on_event: OnEvent | None = None,
) -> Agent:
    """创建一个带内置工具并可组合额外工具执行器的 Agent。"""

    builtin = BuiltinTools(
        agent_registry=agent_registry,
        cwd=cwd,
        command_timeout=command_timeout,
        allowed_paths=[skill.path.parent for skill in skills.skills.values()]
        if skills
        else None,
        allowed_commands=allowed_commands,
    )
    tool_executor = CompositeToolExecutor([builtin, *(executors or [])])

    return Agent(
        provider=provider,
        tools=tools,
        tool_executor=tool_executor,
        preprocessor=preprocessor,
        agent_registry=agent_registry,
        skills=skills,
        description=description,
        cwd=cwd,
        max_iterations=max_iterations,
        command_timeout=command_timeout,
        allowed_commands=allowed_commands,
        system_prompt=system_prompt,
        on_event=on_event,
    )
