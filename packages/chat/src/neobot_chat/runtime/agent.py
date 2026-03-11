from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import StatePreprocessor, ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    Message,
    OnEvent,
    State,
    ToolCall,
    ToolDefinition,
)
from neobot_chat.skills.inject import build_skill_preprocessor
from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.tools.builtin import BuiltinTools
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.utils import parse_tool_args


class Agent:
    """基于 LLM 的智能代理，自动处理工具调用循环"""

    def __init__(
        self,
        provider: Provider,
        *,
        tools: list[ToolDefinition] | None = None,
        tool_executor: ToolExecutor | None = None,
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
    ):
        self.provider = provider

        self.tool_executor = tool_executor or self._build_legacy_tool_executor(
            agent_registry=agent_registry,
            skills=skills,
            cwd=cwd,
            command_timeout=command_timeout,
            allowed_commands=allowed_commands,
        )
        self.tool_definitions = list(tools or [])
        self.custom_tools = self.tool_definitions
        self.skills = skills
        self.description = description
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.on_event = on_event
        self.preprocessor = preprocessor or self._build_legacy_preprocessor(skills)

    async def invoke(self, state: State) -> State:
        state, tools, messages = self._prepare(state)

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i})
            response = await self.provider.chat(messages, tools=tools)
            messages.append(response)

            tool_calls = response.get("tool_calls")
            self._emit_response(response, tool_calls)

            if not tool_calls:
                break
            await self._run_tools(tool_calls, messages)

        return {**state, "messages": messages}

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        """流式执行：yield 文本 delta，工具调用透明处理"""
        state, tools, messages = self._prepare(state)

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i, "stream": True})

            response: Message | None = None
            async for chunk in self.provider.stream(messages, tools=tools):
                if chunk.delta:
                    yield ChatChunk(delta=chunk.delta)
                chunk_message = chunk.message
                if chunk_message is not None:
                    response = chunk_message

            if response is None:
                break
            messages.append(response)

            tool_calls = response.get("tool_calls")
            self._emit_response(response, tool_calls)

            if not tool_calls:
                break
            await self._run_tools(tool_calls, messages)

        yield ChatChunk(state={**state, "messages": messages})

    async def close(self) -> None:
        """释放底层 provider 资源。"""
        await self.tool_executor.close()
        await self.provider.close()

    def _all_tools(self) -> list[ToolDefinition]:
        return self.tool_executor.definitions() + self.tool_definitions

    def _prepare(
        self, state: State
    ) -> tuple[State, list[ToolDefinition] | None, list[Message]]:
        tools = self._all_tools() or None
        if self.preprocessor:
            state = self.preprocessor(state)
        messages: list[Message] = list(state.get("messages", []))

        has_system = any(m.get("role") == "system" for m in messages)

        if self.system_prompt:
            if has_system:
                for i, m in enumerate(messages):
                    if m.get("role") == "system":
                        messages[i] = {"role": "system", "content": self.system_prompt}
                        break
            else:
                messages.insert(0, {"role": "system", "content": self.system_prompt})
        elif tools:
            names = ", ".join(t["function"]["name"] for t in tools)
            tool_instruction = (
                f"You have access to the following tools: {names}. "
                "When the user asks you to perform actions "
                "(file operations, running commands, etc.), "
                "you MUST use the provided tool functions. "
                "Do NOT write code or commands in your text response."
            )
            if has_system:
                for i, m in enumerate(messages):
                    if m.get("role") == "system":
                        messages[i]["content"] = (
                            tool_instruction + "\n\n" + m["content"]
                        )
                        break
            else:
                messages.insert(0, {"role": "system", "content": tool_instruction})

        return state, tools, messages

    def _emit(self, event: str, data: dict) -> None:
        if self.on_event:
            self.on_event(event, data)

    @staticmethod
    def _build_legacy_preprocessor(
        skills: SkillRegistry | None,
    ) -> StatePreprocessor | None:
        return build_skill_preprocessor(skills)

    @staticmethod
    def _build_legacy_tool_executor(
        *,
        agent_registry: AgentRegistry | None,
        skills: SkillRegistry | None,
        cwd: str | Path | None,
        command_timeout: int,
        allowed_commands: list[str] | None,
    ) -> ToolExecutor:
        allowed_paths = []
        if skills:
            for skill in skills.skills.values():
                allowed_paths.append(skill.path.parent)

        return BuiltinTools(
            agent_registry=agent_registry,
            cwd=cwd,
            command_timeout=command_timeout,
            allowed_paths=allowed_paths,
            allowed_commands=allowed_commands,
        )

    def _emit_response(
        self, response: Message, tool_calls: list[ToolCall] | None
    ) -> None:
        self._emit(
            "llm_end",
            {
                "content": (response.get("content") or "")[:200],
                "tool_calls": [tc["function"]["name"] for tc in (tool_calls or [])],
            },
        )

    async def _run_tools(
        self, tool_calls: list[ToolCall], messages: list[Message]
    ) -> None:
        for call in tool_calls:
            name = call["function"]["name"]
            raw = call["function"]["arguments"]
            args = parse_tool_args(raw)

            self._emit("tool_start", {"name": name, "args": args})
            try:
                result = await self.tool_executor.execute(name, args)
            except Exception as e:
                result = f"Error: {type(e).__name__}: {e}"
                self._emit("error", {"name": name, "error": result})
            else:
                self._emit("tool_end", {"name": name, "result": result[:500]})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )
