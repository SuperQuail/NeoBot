from __future__ import annotations

from pathlib import Path
from typing import Any

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


async def test_invoke_returns_fallback_state_on_provider_error(tmp_path: Path):
    """provider.chat 抛异常时 invoke 必须返回兜底状态而不向调用方抛错。"""
    # Arrange
    provider = FakeProvider([ProviderError("API down")])
    agent = Agent(provider, cwd=tmp_path, max_iterations=3)
    try:
        # Act
        state = await agent.invoke({"messages": [{"role": "user", "content": "hi"}]})

        # Assert
        assert isinstance(state, dict)
        assert "messages" in state
        last = state["messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"].startswith("Error: ProviderError: API down")
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
