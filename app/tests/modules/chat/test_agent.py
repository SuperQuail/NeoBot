from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from neobot_chat.runtime.agent import Agent
from neobot_chat.schema.exceptions import ProviderError
from neobot_chat.schema.types import ChatChunk, ToolAccessPolicy, ToolGuardContext
from neobot_chat.tools.toolset import ToolSpec, Toolset


class FakeProvider:
    """按预定义序列返回 chat 响应的假 Provider；序列中的异常原样抛出。"""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def chat(self, messages: list[dict], tools=None) -> dict:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self) -> None:
        return None


class _StreamingProvider:
    """流式假 Provider：固定输出两段 delta 与一条完整消息。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict], tools=None) -> dict:
        raise AssertionError("stream_invoke 不应调用 chat")

    async def stream(self, messages: list[dict], tools=None):
        self.calls += 1
        yield ChatChunk(delta="hel")
        yield ChatChunk(delta="lo")
        yield ChatChunk(message={"role": "assistant", "content": "hello"})

    async def close(self) -> None:
        return None


class _StreamThenFailProvider:
    """流式假 Provider：先产出一段 delta，再抛异常（模拟传输中断）。"""

    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls = 0

    async def chat(self, messages: list[dict], tools=None) -> dict:
        raise AssertionError("stream_invoke 不应调用 chat")

    async def stream(self, messages: list[dict], tools=None):
        self.calls += 1
        yield ChatChunk(delta="半句")
        raise self._error

    async def close(self) -> None:
        return None


class _BoomExecutor:
    """execute 必抛 RuntimeError 的假工具执行器。"""

    async def execute(self, name: str, args: dict) -> str:
        raise RuntimeError("boom")

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "boom_tool", "parameters": {"type": "object"}}}]

    async def close(self) -> None:
        return None


class _DenyExecutor:
    """记录调用次数、可被 deny 策略拦截的假工具执行器。"""

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, name: str, args: dict) -> str:
        self.calls += 1
        return "secret data"

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "secret_tool", "parameters": {"type": "object"}}}]

    async def close(self) -> None:
        return None


class _LoadingExecutor:
    """第一次调用后动态多出一个工具的假执行器（模拟 skills__load_tools）。"""

    def __init__(self) -> None:
        self.loaded = False
        self.calls: list[str] = []

    def definitions(self) -> list[dict]:
        tools = [_tool_def("load_tools")]
        if self.loaded:
            tools.append(_tool_def("loaded_tool"))
        return tools

    async def execute(self, name: str, args: dict) -> str:
        self.calls.append(name)
        self.loaded = True
        return "ok"

    async def close(self) -> None:
        return None


class _LiveToolset(Toolset):
    """definitions() 每次从执行器重算的工具集（同 LiveToolset 契约）。"""

    def definitions(self) -> list[dict]:
        return self.executor.definitions()


class _ToolRecordingProvider(FakeProvider):
    """记录每次请求实际携带的工具列表。"""

    def __init__(self, responses: list[Any]) -> None:
        super().__init__(responses)
        self.tool_lists: list[list[dict] | None] = []

    async def chat(self, messages: list[dict], tools=None) -> dict:
        self.tool_lists.append(tools)
        return await super().chat(messages, tools)


def _tool_def(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"type": "object"}},
    }


def _allow_resolver(args: dict, context: ToolGuardContext, policy: ToolAccessPolicy):
    return policy.default_rule


def _deny_resolver(args: dict, context: ToolGuardContext, policy: ToolAccessPolicy):
    from neobot_chat.schema.types import ToolAccessRule

    return ToolAccessRule(action="deny")


def _tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


async def test_invoke_single_turn_appends_final_message(tmp_path: Path):
    """无工具调用的单轮对话：invoke 必须返回带 system/user/assistant 的消息列表且只调用一次 provider。"""
    # Arrange
    provider = FakeProvider([{"role": "assistant", "content": "hello"}])
    agent = Agent(provider, cwd=tmp_path, max_iterations=5)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})

        # Assert
        assert provider.calls == 1
        roles = [m["role"] for m in state["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert state["messages"][-1]["content"] == "hello"
        assert state["messages"][0]["role"] == "system"
    finally:
        await agent.close()


async def test_invoke_multi_turn_tool_loop_runs_tools_and_finishes(tmp_path: Path):
    """多轮工具循环：工具结果必须以 tool 角色携带 tool_call_id 追加，随后继续下一轮 LLM 调用。"""
    # Arrange
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    read_call = _tool_call("call_1", "read_file", '{"path": "a.txt"}')
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [read_call]},
            {"role": "assistant", "content": "done"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "read a.txt"}]})

        # Assert
        assert provider.calls == 2
        roles = [m["role"] for m in state["messages"]]
        assert roles == ["system", "user", "assistant", "tool", "assistant"]
        tool_message = state["messages"][3]
        assert tool_message["tool_call_id"] == "call_1"
        assert tool_message["content"] == "hello"
        assert state["messages"][2]["tool_calls"][0]["function"]["name"] == "read_file"
        assert state["messages"][-1]["content"] == "done"
    finally:
        await agent.close()


async def test_invoke_truncates_at_max_iterations(tmp_path: Path):
    """LLM 持续请求工具时 invoke 必须在 max_iterations 次调用后截断返回而不死循环。"""
    # Arrange
    read_call = _tool_call("call_x", "read_file", '{"path": "a.txt"}')
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [read_call]},
            {"role": "assistant", "content": None, "tool_calls": [read_call]},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=2)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "loop"}]})

        # Assert
        assert provider.calls == 2
        assert state["messages"][-1]["role"] == "tool"
        assert state["messages"][-1]["content"].startswith("Error: File not found")
    finally:
        await agent.close()


async def test_invoke_continues_after_tool_execution_error(tmp_path: Path):
    """工具执行抛异常时 invoke 必须把错误写入 tool 消息并继续后续 LLM 调用。"""
    # Arrange
    boom_toolset = Toolset(
        executor=_BoomExecutor(),
        specs=[ToolSpec(_boom_def(), _allow_resolver)],
    )
    boom_call = _tool_call("call_1", "boom_tool", "{}")
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [boom_call]},
            {"role": "assistant", "content": "recovered"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5, toolset=boom_toolset)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "boom"}]})

        # Assert
        assert provider.calls == 2
        tool_message = next(m for m in state["messages"] if m["role"] == "tool")
        assert tool_message["content"].startswith("Error: RuntimeError: boom")
        assert state["messages"][-1]["content"] == "recovered"
    finally:
        await agent.close()


async def test_invoke_handles_invalid_tool_arguments_json(tmp_path: Path):
    """工具参数 JSON 解析失败时必须追加错误 tool 消息并继续下一轮 LLM 调用。"""
    # Arrange
    bad_call = _tool_call("call_1", "read_file", "{not-json")
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [bad_call]},
            {"role": "assistant", "content": "ok"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "bad args"}]})

        # Assert
        assert provider.calls == 2
        tool_message = next(m for m in state["messages"] if m["role"] == "tool")
        assert "工具参数 JSON 解析失败" in tool_message["content"]
        assert state["messages"][-1]["content"] == "ok"
    finally:
        await agent.close()


async def test_invoke_denies_policy_denied_tool_without_execution(tmp_path: Path):
    """access_resolver 返回 deny 的工具必须被拦截：追加拒绝消息且执行器不被调用。"""
    # Arrange
    deny_executor = _DenyExecutor()
    secret_toolset = Toolset(
        executor=deny_executor,
        specs=[ToolSpec(_secret_def(), _deny_resolver)],
    )
    secret_call = _tool_call("call_1", "secret_tool", "{}")
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [secret_call]},
            {"role": "assistant", "content": "fine"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5, toolset=secret_toolset)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "secret"}]})

        # Assert
        tool_message = next(m for m in state["messages"] if m["role"] == "tool")
        assert "denied by policy: secret_tool" in tool_message["content"]
        assert deny_executor.calls == 0
        assert state["messages"][-1]["content"] == "fine"
    finally:
        await agent.close()


async def test_merged_live_toolset_is_exposed_and_refreshed_after_tool_use(tmp_path: Path):
    """Agent.merge 必须保留动态 definitions：首轮可见，加载后下一轮立即生效。"""
    executor = _LoadingExecutor()
    toolset = _LiveToolset(executor=executor, specs=[])
    provider = _ToolRecordingProvider(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_tool_call("call_1", "load_tools", "{}")],
            },
            {"role": "assistant", "content": "done"},
        ]
    )
    agent = Agent(
        provider, cwd=tmp_path, toolset=toolset, include_builtin_tools=False,
        max_iterations=5,
    )
    try:
        await agent.invoke({"messages": [{"role": "user", "content": "load"}]})
    finally:
        await agent.close()

    first = {tool["function"]["name"] for tool in provider.tool_lists[0] or []}
    second = {tool["function"]["name"] for tool in provider.tool_lists[1] or []}
    assert first == {"load_tools"}
    assert second == {"load_tools", "loaded_tool"}
    assert executor.calls == ["load_tools"]


async def test_invoke_reports_unknown_tool_error_in_messages(tmp_path: Path):
    """调用未注册工具必须把 Unknown tool 错误写入 tool 消息并继续循环。"""
    # Arrange
    ghost_call = _tool_call("call_1", "ghost_tool", "{}")
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [ghost_call]},
            {"role": "assistant", "content": "ok"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "ghost"}]})

        # Assert
        tool_message = next(m for m in state["messages"] if m["role"] == "tool")
        assert tool_message["content"].startswith("Error: ToolError: Unknown tool: ghost_tool")
        assert provider.calls == 2
    finally:
        await agent.close()


async def test_invoke_raises_and_keeps_history_clean_on_provider_error(tmp_path: Path):
    """provider.chat 抛异常时 invoke 必须显式失败，且不把错误写进对话历史。

    旧行为是把 `Error: ...` 当成 assistant 回复返回，调用方无法区分"模型回复"与
    "调用失败"，错误串还会随历史回灌 —— 见 fix(12) §4.2。
    """
    # Arrange
    provider = FakeProvider([ProviderError("API down")])
    agent = Agent(provider, cwd=tmp_path, max_iterations=3)
    try:
        # Act / Assert
        with pytest.raises(ProviderError) as excinfo:
            await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})

        assert "API down" in str(excinfo.value)
        assert provider.calls == 1
    finally:
        await agent.close()


async def test_invoke_wraps_unknown_provider_exception_with_context(tmp_path: Path):
    """非 ProviderError 的底层异常要带上 provider/原因，便于编排层降级与归因。"""
    provider = FakeProvider([RuntimeError("socket closed")])
    agent = Agent(provider, cwd=tmp_path, max_iterations=3)
    try:
        with pytest.raises(ProviderError) as excinfo:
            await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})

        error = excinfo.value
        assert error.original_name == "RuntimeError"
        assert error.provider
        assert error.iteration == 0
        assert error.stream_started is False
    finally:
        await agent.close()


async def test_stream_invoke_raises_with_stream_started_flag(tmp_path: Path):
    """流式路径：已产出 delta 后失败必须带 stream_started=True，调用方据此不重放。"""
    provider = _StreamThenFailProvider(RuntimeError("connection reset"))
    agent = Agent(provider, cwd=tmp_path, max_iterations=3)
    try:
        received: list[str] = []
        with pytest.raises(ProviderError) as excinfo:
            async for chunk in agent.stream_invoke(
                {"messages": [{"role": "user", "content": "hi"}]}
            ):
                if chunk.delta:
                    received.append(chunk.delta)

        assert received == ["半句"]
        assert excinfo.value.stream_started is True
        assert excinfo.value.original_name == "RuntimeError"
    finally:
        await agent.close()


async def test_invoke_emits_tool_and_llm_events(tmp_path: Path):
    """多轮调用必须按顺序发出 llm_start/llm_end/tool_start/tool_end 事件。"""
    # Arrange
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    read_call = _tool_call("call_1", "read_file", '{"path": "a.txt"}')
    events: list[str] = []
    provider = FakeProvider(
        [
            {"role": "assistant", "content": None, "tool_calls": [read_call]},
            {"role": "assistant", "content": "done"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path, max_iterations=5, on_event=lambda ev, data: events.append(ev))
    try:
        # Act
        await agent.invoke({"messages": [{"role": "user", "content": "read"}]})

        # Assert
        assert events == [
            "llm_start",
            "llm_end",
            "tool_start",
            "tool_end",
            "llm_start",
            "llm_end",
        ]
    finally:
        await agent.close()


async def test_stream_invoke_yields_deltas_then_final_state(tmp_path: Path):
    """stream_invoke 必须逐段透出 delta 并在末尾产出携带最终消息的 state chunk。"""
    # Arrange
    provider = _StreamingProvider()
    agent = Agent(provider, cwd=tmp_path, max_iterations=5)
    try:
        # Act
        chunks = [chunk async for chunk in agent.stream_invoke({"messages": []})]

        # Assert
        assert provider.calls == 1
        deltas = [chunk.delta for chunk in chunks if chunk.delta]
        assert deltas == ["hel", "lo"]
        state_chunks = [chunk.state for chunk in chunks if chunk.state is not None]
        assert len(state_chunks) == 1
        assert state_chunks[0]["messages"][-1]["content"] == "hello"
    finally:
        await agent.close()


def _boom_def() -> dict:
    return {"type": "function", "function": {"name": "boom_tool", "parameters": {"type": "object"}}}


def _secret_def() -> dict:
    return {"type": "function", "function": {"name": "secret_tool", "parameters": {"type": "object"}}}


async def test_invoke_supports_unbounded_iterations(tmp_path: Path):
    """max_iterations=None 表示不限制工具轮次（自修复 Agent 使用）。"""
    provider = FakeProvider([{"role": "assistant", "content": "done"}])
    agent = Agent(provider, cwd=tmp_path, max_iterations=None)
    try:
        result = await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
        assert provider.calls == 1
        assert result["messages"][-1]["content"] == "done"
    finally:
        await agent.close()


async def test_invoke_calls_message_compactor_before_model(tmp_path: Path):
    """构造 Agent 时接到 message_compactor：每轮模型调用前先尝试压缩上下文。"""
    provider = FakeProvider([{"role": "assistant", "content": "done"}])
    seen: list[list[str]] = []

    async def compact(messages):
        seen.append([str(m.get("role") or "") for m in messages])
        return messages

    agent = Agent(provider, cwd=tmp_path, max_iterations=1, message_compactor=compact)
    try:
        await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
    finally:
        await agent.close()
    assert seen and seen[0][0] == "system"
