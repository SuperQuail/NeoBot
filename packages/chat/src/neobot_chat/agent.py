from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from neobot_chat.providers.base import Provider
from neobot_chat.skills.inject import inject_skills
from neobot_chat.skills.registry import SkillRegistry
from neobot_chat.tools.builtin import BuiltinTools
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.types import ChatChunk, OnEvent, State
from neobot_chat.utils import parse_tool_args


class Agent:
    """基于 LLM 的智能代理，自动处理工具调用循环"""

    def __init__(
            self,
            provider: Provider,
            *,
            tools: list[dict] | None = None,
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

        # 收集允许访问的路径：skills 目录
        allowed_paths = []
        if skills:
            for skill in skills.skills.values():
                allowed_paths.append(skill.path.parent)

        self.builtin_tools = BuiltinTools(
            agent_registry=agent_registry,
            cwd=cwd,
            command_timeout=command_timeout,
            allowed_paths=allowed_paths,
            allowed_commands=allowed_commands,
        )
        self.custom_tools = tools or []
        self.skills = skills
        self.description = description
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.on_event = on_event

    # ── 公共 API ──

    async def invoke(self, state: State) -> State:
        tools, messages = self._prepare(state)

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
        tools, messages = self._prepare(state)

        for i in range(self.max_iterations):
            self._emit("llm_start", {"iteration": i, "stream": True})

            response: dict | None = None
            async for chunk in self.provider.stream(messages, tools=tools):
                if chunk.delta:
                    yield ChatChunk(delta=chunk.delta)
                if chunk.message:
                    response = chunk.message

            if response is None:
                break
            messages.append(response)

            tool_calls = response.get("tool_calls")
            self._emit_response(response, tool_calls)

            if not tool_calls:
                break
            await self._run_tools(tool_calls, messages)

        yield ChatChunk(state={**state, "messages": messages})

    # ── 内部实现 ──

    def _all_tools(self) -> list[dict]:
        return self.builtin_tools.definitions() + self.custom_tools

    def _prepare(self, state: State) -> tuple[list[dict] | None, list[dict]]:
        tools = self._all_tools() or None
        messages = list(inject_skills(self.skills, state).get("messages", []))

        # 处理 system prompt：优先级为 用户提供的 system_prompt > 现有 system message > 默认工具提示
        has_system = any(m.get("role") == "system" for m in messages)

        if self.system_prompt:
            # 用户明确提供了 system_prompt，优先使用
            if has_system:
                for i, m in enumerate(messages):
                    if m.get("role") == "system":
                        messages[i] = {"role": "system", "content": self.system_prompt}
                        break
            else:
                messages.insert(0, {"role": "system", "content": self.system_prompt})
        elif tools:
            # 有工具时，确保工具使用指令存在
            names = ", ".join(t["function"]["name"] for t in tools)
            tool_instruction = (
                f"You have access to the following tools: {names}. "
                "When the user asks you to perform actions "
                "(file operations, running commands, etc.), "
                "you MUST use the provided tool functions. "
                "Do NOT write code or commands in your text response."
            )
            if has_system:
                # 有现有 system message（来自 skills），将工具指令前置
                for i, m in enumerate(messages):
                    if m.get("role") == "system":
                        messages[i]["content"] = tool_instruction + "\n\n" + m["content"]
                        break
            else:
                # 没有 system message，添加工具指令
                messages.insert(0, {"role": "system", "content": tool_instruction})

        return tools, messages

    def _emit(self, event: str, data: dict) -> None:
        if self.on_event:
            self.on_event(event, data)

    def _emit_response(
            self, response: dict, tool_calls: list[dict] | None
    ) -> None:
        self._emit("llm_end", {
            "content": (response.get("content") or "")[:200],
            "tool_calls": [
                tc["function"]["name"] for tc in (tool_calls or [])
            ],
        })

    async def _run_tools(
            self, tool_calls: list[dict], messages: list[dict]
    ) -> None:
        for call in tool_calls:
            name = call["function"]["name"]
            raw = call["function"]["arguments"]
            args = parse_tool_args(raw)

            self._emit("tool_start", {"name": name, "args": args})
            try:
                result = await self.builtin_tools.execute(name, args)
            except Exception as e:
                result = f"Error: {type(e).__name__}: {e}"
                self._emit("error", {"name": name, "error": result})
            else:
                self._emit("tool_end", {"name": name, "result": result[:500]})

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })
