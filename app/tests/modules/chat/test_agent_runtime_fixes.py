from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from neobot_chat.runtime.agent import Agent
from neobot_chat.schema.types import ToolAccessPolicy, ToolGuardContext
from neobot_chat.tools.builtin import build_builtin_toolset
from neobot_chat.tools.toolset import ToolSpec, Toolset


class _Provider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict], tools=None) -> dict:
        self.calls.append(list(messages))
        return self.responses.pop(0)

    async def close(self) -> None:
        return None


class _ValueExecutor:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def execute(self, name: str, args: dict) -> Any:
        return self.value

    def definitions(self) -> list[dict]:
        return [_tool_definition("value_tool")]

    async def close(self) -> None:
        return None


class _RecordingRegistry:
    names = ["demo.helper"]

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def list_agents(self, agent: str | None = None) -> str:
        return "agents"

    async def delegate(self, **kwargs: Any) -> str:
        self.kwargs = kwargs
        return "delegated"


def _tool_definition(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"type": "object"}},
    }


def _allow_resolver(args: dict, context: ToolGuardContext, policy: ToolAccessPolicy):
    return policy.default_rule


def _tool_call(arguments: str, *, name: str = "read_file") -> dict:
    return {
        "id": "call-1",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


@pytest.mark.parametrize(
    "arguments, expected_type",
    [("[]", "list"), ("42", "int"), ("null", "null")],
)
async def test_non_object_json_tool_arguments_are_reported_and_loop_continues(
    tmp_path: Path, arguments: str, expected_type: str
) -> None:
    provider = _Provider(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_tool_call(arguments)],
            },
            {"role": "assistant", "content": "recovered"},
        ]
    )
    agent = Agent(provider, cwd=tmp_path)

    try:
        state = await agent.invoke({"messages": [{"role": "user", "content": "run"}]})
    finally:
        await agent.close()

    tool_message = next(
        message for message in state["messages"] if message["role"] == "tool"
    )
    assert "工具参数必须是 JSON 对象" in tool_message["content"]
    assert expected_type in tool_message["content"]
    assert state["messages"][-1]["content"] == "recovered"
    assert len(provider.calls) == 2


async def test_non_string_executor_result_is_normalized_before_event_and_message(
    tmp_path: Path,
) -> None:
    value = {"ok": True}
    executor = _ValueExecutor(value)
    toolset = Toolset(
        executor=executor,
        specs=[ToolSpec(_tool_definition("value_tool"), _allow_resolver)],
    )
    provider = _Provider(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_tool_call("{}", name="value_tool")],
            },
            {"role": "assistant", "content": "done"},
        ]
    )
    events: list[tuple[str, dict]] = []
    agent = Agent(
        provider,
        cwd=tmp_path,
        toolset=toolset,
        on_event=lambda event, data: events.append((event, data)),
    )

    try:
        state = await agent.invoke({"messages": [{"role": "user", "content": "run"}]})
    finally:
        await agent.close()

    expected = str(value)
    tool_message = next(
        message for message in state["messages"] if message["role"] == "tool"
    )
    tool_end = next(data for event, data in events if event == "tool_end")
    assert tool_message["content"] == expected
    assert tool_end["result"] == expected


async def test_prepare_filters_non_mapping_messages(tmp_path: Path) -> None:
    provider = _Provider([{"role": "assistant", "content": "done"}])
    agent = Agent(provider, cwd=tmp_path)

    try:
        state = await agent.invoke(
            {
                "messages": [
                    None,
                    "junk",
                    7,
                    {"role": "user", "content": "valid"},
                ]
            }
        )
    finally:
        await agent.close()

    assert all(isinstance(message, dict) for message in state["messages"])
    assert [
        message["content"] for message in provider.calls[0] if message["role"] == "user"
    ] == ["valid"]


async def test_builtin_delegate_schema_and_execution_support_registry_arguments(
    tmp_path: Path,
) -> None:
    registry = _RecordingRegistry()
    toolset = build_builtin_toolset(cwd=tmp_path, agent_registry=registry)
    delegate = next(spec for spec in toolset.specs if spec.name == "delegate")
    properties = delegate.definition["function"]["parameters"]["properties"]

    try:
        result = await toolset.executor.execute(
            "delegate",
            {
                "agent": "demo.helper",
                "task": "continue",
                "previous_response": "partial",
                "session_id": "session-1",
                "context": "conversation context",
                "hallucinated": "ignored",
            },
        )
    finally:
        await toolset.executor.close()

    assert {"previous_response", "session_id", "context"} <= properties.keys()
    task_properties = properties["tasks"]["items"]["properties"]
    assert {"previous_response", "session_id"} <= task_properties.keys()
    assert result == "delegated"
    assert registry.kwargs == {
        "agent": "demo.helper",
        "task": "continue",
        "tasks": None,
        "previous_response": "partial",
        "session_id": "session-1",
        "context": "conversation context",
    }


async def test_maintenance_agent_closes_when_cycle_is_cancelled(monkeypatch) -> None:
    from neobot_app import bootstrap
    from neobot_chat.runtime import agent as agent_module

    instances: list[Any] = []

    class _MaintenanceAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.close_count = 0
            instances.append(self)

        async def invoke(self, state: dict) -> dict:
            raise asyncio.CancelledError

        async def close(self) -> None:
            self.close_count += 1

    class _SkillManager:
        def get_tools(self) -> list[dict]:
            return []

        def get_all_tools(self) -> list[dict]:
            # 独立 Agent(沙箱维护)自建工具集走 get_all_tools
            return []

        async def execute(self, name: str, args: dict) -> str:
            return "unused"

    class _Logger:
        def info(self, message: str) -> None:
            return None

        def warning(self, message: str) -> None:
            return None

    async def _skip_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(agent_module, "Agent", _MaintenanceAgent)
    monkeypatch.setattr(bootstrap.asyncio, "sleep", _skip_sleep)
    maintenance = bootstrap._make_maintenance_coro(
        provider=object(),
        skill_manager=_SkillManager(),
        sandbox_components={},
        data_dir=Path("."),
        admin_id="admin",
        logger=_Logger(),
    )

    with pytest.raises(asyncio.CancelledError):
        await maintenance

    assert len(instances) == 1
    assert instances[0].close_count == 1
