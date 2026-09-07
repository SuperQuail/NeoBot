from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import StatePreprocessor, ToolGuard
from neobot_chat.schema.types import (
    ChatChunk,
    Message,
    OnEvent,
    State,
    ToolAccessAction,
    ToolAccessRule,
    ToolCall,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.skills.inject import build_skill_preprocessor
from neobot_chat.runtime.prompt import SystemPromptState
from neobot_chat.skills.registry import Skill, SkillRegistry
from neobot_chat.tools.builtin import build_builtin_toolset
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.tools.toolset import Toolset
from neobot_chat.utils import parse_tool_args

SILENT_HEARTBEAT: ContextVar[Callable[[], None] | None] = ContextVar(
    "silent_heartbeat", default=None
)


class Agent:
    """基于 LLM 的智能代理，自动处理工具调用循环"""

    def __init__(
        self,
        provider: Provider,
        *,
        toolset: Toolset | None = None,
        include_builtin_tools: bool = True,
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
        on_model_usage: Callable[..., Any] | None = None,
        logger: Logger = NullLogger(),
        output: Any | None = None,
    ):
        self._logger = logger
        self.provider = provider
        self.cwd = Path(cwd).resolve() if cwd is not None else None
        self.allowed_commands = list(allowed_commands or [])
        self.allowed_paths = self._build_allowed_paths(skills)
        self.tool_guard = tool_guard
        self._strict_tools = not include_builtin_tools
        self._on_model_usage = on_model_usage

        builtin_toolset = build_builtin_toolset(
            agent_registry=agent_registry,
            cwd=cwd,
            command_timeout=command_timeout,
            # 复用已 resolve 并去重的 allowed_paths 快照（去掉 cwd 一份，BuiltinTools 会自行加上），
            # 避免未 resolve 的相对路径与 _path_resolver 的 resolve 结果比较失配
            allowed_paths=[p for p in self.allowed_paths if self.cwd is None or p != self.cwd],
            allowed_commands=allowed_commands,
            output=output,
        )
        # Explicit tool-only agents must not implicitly expose host filesystem/shell tools.
        self.toolset = Toolset.merge([builtin_toolset if include_builtin_tools else None, toolset])
        self._tool_specs = {spec.name: spec for spec in self.toolset.specs}

        self.skills = skills
        self.description = description
        self.max_iterations = max_iterations
        self.command_timeout = command_timeout
        self.system_prompt = system_prompt
        self.on_event = on_event
        self.preprocessor = preprocessor or self._build_legacy_preprocessor(skills)
        self._close_task: asyncio.Task | None = None

    async def invoke(self, state: State) -> State:
        state, tools, messages = self._prepare(state)
        heartbeat = SILENT_HEARTBEAT.get()

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i})
            try:
                response = await self.provider.chat(messages, tools=tools)
            except Exception as exc:
                error_text = f"Error: {type(exc).__name__}: {exc}"
                self._emit("error", {"provider": True, "error": error_text})
                messages.append({"role": "assistant", "content": error_text})
                break
            if heartbeat:
                heartbeat()
            messages.append(response)

            tool_calls = response.get("tool_calls")
            self._emit_response(response, tool_calls)

            if self._on_model_usage is not None:
                usage = (response.get("extensions") or {}).get("usage")
                if isinstance(usage, dict):
                    try:
                        await self._on_model_usage(
                            model_name=getattr(self.provider, "model", ""),
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    except Exception:
                        pass

            if not tool_calls:
                break
            await self._run_tools(tool_calls, messages, heartbeat=heartbeat)

        return {**state, "messages": messages}

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        state, tools, messages = self._prepare(state)
        heartbeat = SILENT_HEARTBEAT.get()

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i, "stream": True})

            response: Message | None = None
            try:
                async for chunk in self.provider.stream(messages, tools=tools):
                    if chunk.reasoning_delta:
                        yield ChatChunk(reasoning_delta=chunk.reasoning_delta)
                    if chunk.delta:
                        yield ChatChunk(delta=chunk.delta)
                    chunk_message = chunk.message
                    if chunk_message is not None:
                        response = chunk_message
                        yield ChatChunk(message=chunk_message)
            except Exception as exc:
                error_text = f"Error: {type(exc).__name__}: {exc}"
                self._emit("error", {"provider": True, "error": error_text})
                messages.append({"role": "assistant", "content": error_text})
                yield ChatChunk(state={**state, "messages": messages})
                return

            if response is None:
                break
            if heartbeat:
                heartbeat()
            messages.append(response)

            tool_calls = response.get("tool_calls")
            self._emit_response(response, tool_calls)

            if self._on_model_usage is not None:
                usage = (response.get("extensions") or {}).get("usage")
                if isinstance(usage, dict):
                    try:
                        await self._on_model_usage(
                            model_name=getattr(self.provider, "model", ""),
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    except Exception:
                        pass

            if not tool_calls:
                break
            await self._run_tools(tool_calls, messages, heartbeat=heartbeat)

        yield ChatChunk(state={**state, "messages": messages})

    async def close(self) -> None:
        if self._close_task is None or (
            self._close_task.done()
            and (self._close_task.cancelled() or self._close_task.exception() is not None)
        ):
            self._close_task = asyncio.create_task(self._close_resources())
        await asyncio.shield(self._close_task)

    async def _close_resources(self) -> None:
        results = await asyncio.gather(
            self.toolset.executor.close(), self.provider.close(), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    def _all_tools(self) -> list[ToolDefinition]:
        return self.toolset.definitions()

    def _prepare(
        self, state: State
    ) -> tuple[State, list[ToolDefinition] | None, list[Message]]:
        tools = self._all_tools() or None
        if self.preprocessor:
            state = self.preprocessor(state)
        raw_messages = state.get("messages", [])
        messages: list[Message] = []
        if isinstance(raw_messages, (list, tuple)):
            messages = [
                cast(Message, dict(message))
                for message in raw_messages
                if isinstance(message, Mapping)
            ]
        matched_skills = state.get("_matched_skills") if self.skills else None
        # state 由外部注入时可能携带非 Skill 数据，过滤掉避免 set_skills 渲染时崩溃
        if isinstance(matched_skills, (list, tuple)):
            matched_skills = [s for s in matched_skills if isinstance(s, Skill)] or None
        else:
            matched_skills = None

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
            return "deny" if self._strict_tools else "allow"
        rule = spec.access_resolver(args, self._build_tool_guard_context(), self.toolset.policy)
        return self._resolve_rule(rule)

    async def _ask_tool_guard(self, name: str, args: dict) -> bool:
        if self.tool_guard is None:
            return False
        result = self.tool_guard(name, args, self._build_tool_guard_context())
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def _run_tools(
        self,
        tool_calls: list[ToolCall],
        messages: list[Message],
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        for call in tool_calls:
            name = call["function"]["name"]
            raw = call["function"]["arguments"]
            try:
                parsed_args = parse_tool_args(raw)
            except Exception as exc:
                result = f"Error: 工具参数 JSON 解析失败: {exc}"
                self._emit("error", {"name": name, "error": result})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                continue
            if not isinstance(parsed_args, Mapping):
                arg_type = "null" if parsed_args is None else type(parsed_args).__name__
                result = f"Error: 工具参数必须是 JSON 对象，实际类型: {arg_type}"
                self._emit("error", {"name": name, "error": result})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                continue
            args = dict(parsed_args)
            action = self._decide_tool_action(name, args)

            if action == "ask" and not await self._ask_tool_guard(name, args):
                action = "deny"

            if action == "deny":
                result = f"Error: Tool execution denied by policy: {name}"
                self._emit("tool_denied", {"name": name, "args": args})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                continue

            if heartbeat:
                heartbeat()
            self._emit("tool_start", {"name": name, "args": args})
            try:
                result = str(await self.toolset.executor.execute(name, args))
            except Exception as exc:
                result = f"Error: {type(exc).__name__}: {exc}"
                self._emit("error", {"name": name, "error": result})
            else:
                self._emit("tool_end", {"name": name, "result": result[:500]})

            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
