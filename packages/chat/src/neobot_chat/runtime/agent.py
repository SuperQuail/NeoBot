from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from pathlib import Path

from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import StatePreprocessor, ToolGuard
from neobot_chat.schema.types import (
    ChatChunk,
    Message,
    OnEvent,
    State,
    ToolAccessAction,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolCall,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.skills.inject import build_skill_preprocessor
from neobot_chat.runtime.prompt import SystemPromptState
from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.tools.builtin import build_builtin_toolset
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.tools.toolset import Toolset
from neobot_chat.utils import parse_tool_args


class Agent:
    """基于 LLM 的智能代理，自动处理工具调用循环"""

    def __init__(
        self,
        provider: Provider,
        *,
        toolset: Toolset | None = None,
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
        tool_guard: ToolGuard | None = None,
    ):
        self.provider = provider
        self.cwd = Path(cwd).resolve() if cwd is not None else None
        self.allowed_commands = list(allowed_commands or [])
        self.allowed_paths = self._build_allowed_paths(skills)
        self.tool_guard = tool_guard

        builtin_toolset = build_builtin_toolset(
            agent_registry=agent_registry,
            cwd=cwd,
            command_timeout=command_timeout,
            allowed_paths=[skill.path.parent for skill in skills.skills.values()] if skills else None,
            allowed_commands=allowed_commands,
        )
        self.toolset = Toolset.merge([builtin_toolset, toolset])
        self._tool_specs = {spec.name: spec for spec in self.toolset.specs}

        self.skills = skills
        self.description = description
        self.max_iterations = max_iterations
        self.command_timeout = command_timeout
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
        state, tools, messages = self._prepare(state)

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i, "stream": True})

            response: Message | None = None
            async for chunk in self.provider.stream(messages, tools=tools):
                if chunk.reasoning_delta:
                    yield ChatChunk(reasoning_delta=chunk.reasoning_delta)
                if chunk.delta:
                    yield ChatChunk(delta=chunk.delta)
                chunk_message = chunk.message
                if chunk_message is not None:
                    response = chunk_message
                    yield ChatChunk(message=chunk_message)

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
        await self.toolset.executor.close()
        await self.provider.close()

    def _all_tools(self) -> list[ToolDefinition]:
        return self.toolset.definitions()

    def _prepare(
        self, state: State
    ) -> tuple[State, list[ToolDefinition] | None, list[Message]]:
        tools = self._all_tools() or None
        if self.preprocessor:
            state = self.preprocessor(state)
        messages: list[Message] = list(state.get("messages", []))
        matched_skills = state.get("_matched_skills") if self.skills else None

        system_parts: list[str] = []
        rest: list[Message] = []
        for message in messages:
            if message.get("role") == "system":
                content = message.get("content")
                if isinstance(content, str) and content:
                    system_parts.append(content)
            else:
                rest.append(message)

        prompt_state = SystemPromptState.from_messages(system_parts)
        prompt_state.add_instruction(self.system_prompt)
        prompt_state.set_description(self.description)
        prompt_state.set_tools([t["function"]["name"] for t in tools] if tools else None)
        prompt_state.set_skills(matched_skills)
        prompt_state.set_runtime(
            cwd=str(self.cwd) if self.cwd else None,
            max_iterations=self.max_iterations,
            command_timeout=self.command_timeout,
            allowed_commands=self.allowed_commands or None,
        )
        prompt = prompt_state.render()
        if prompt:
            messages = [{"role": "system", "content": prompt}, *rest]
        else:
            messages = rest

        return state, tools, messages

    def _emit(self, event: str, data: dict) -> None:
        if self.on_event:
            self.on_event(event, data)

    @staticmethod
    def _build_legacy_preprocessor(skills: SkillRegistry | None) -> StatePreprocessor | None:
        return build_skill_preprocessor(skills)

    def _build_allowed_paths(self, skills: SkillRegistry | None) -> list[Path]:
        allowed_paths: list[Path] = []
        if self.cwd is not None:
            allowed_paths.append(self.cwd)
        if skills:
            for skill in skills.skills.values():
                skill_dir = skill.path.parent.resolve()
                if skill_dir not in allowed_paths:
                    allowed_paths.append(skill_dir)
        return allowed_paths

    def _emit_response(self, response: Message, tool_calls: list[ToolCall] | None) -> None:
        self._emit(
            "llm_end",
            {
                "content": response.get("content")[:200] if isinstance(response.get("content"), str) else "",
                "tool_calls": [tc["function"]["name"] for tc in (tool_calls or [])],
            },
        )

    def _build_tool_guard_context(self) -> ToolGuardContext:
        return ToolGuardContext(
            cwd=self.cwd,
            allowed_paths=list(self.allowed_paths),
            allowed_commands=list(self.allowed_commands),
        )

    def _resolve_rule(self, rule: ToolAccessRule) -> ToolAccessAction:
        if rule.action != "ask":
            return rule.action
        if self.tool_guard is not None:
            return "ask"
        return rule.fallback_action or "deny"

    def _decide_tool_action(self, name: str, args: dict) -> ToolAccessAction:
        spec = self._tool_specs.get(name)
        if spec is None:
            return "allow"
        rule = spec.access_resolver(args, self._build_tool_guard_context(), self.toolset.policy)
        return self._resolve_rule(rule)

    async def _ask_tool_guard(self, name: str, args: dict) -> bool:
        if self.tool_guard is None:
            return False
        result = self.tool_guard(name, args, self._build_tool_guard_context())
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def _run_tools(self, tool_calls: list[ToolCall], messages: list[Message]) -> None:
        for call in tool_calls:
            name = call["function"]["name"]
            raw = call["function"]["arguments"]
            args = parse_tool_args(raw)
            action = self._decide_tool_action(name, args)

            if action == "ask" and not await self._ask_tool_guard(name, args):
                action = "deny"

            if action == "deny":
                result = f"Error: Tool execution denied by policy: {name}"
                self._emit("tool_denied", {"name": name, "args": args})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                continue

            self._emit("tool_start", {"name": name, "args": args})
            try:
                result = await self.toolset.executor.execute(name, args)
            except Exception as exc:
                result = f"Error: {type(exc).__name__}: {exc}"
                self._emit("error", {"name": name, "error": result})
            else:
                self._emit("tool_end", {"name": name, "result": result[:500]})

            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
