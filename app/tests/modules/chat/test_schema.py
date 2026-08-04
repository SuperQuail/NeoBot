from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from neobot_chat.schema.types import (
    ChatChunk,
    Message,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolGuardContext,
)


def test_tool_access_policy_default_rules():
    """默认策略必须放行常规操作、对越界路径/未授权命令返回 ask 且回退 deny。"""
    # Arrange
    policy = ToolAccessPolicy()

    # Act / Assert
    assert policy.default_rule.action == "allow"
    assert policy.list_agents_rule.action == "allow"
    assert policy.delegate_rule.action == "ask"
    assert policy.delegate_rule.fallback_action == "allow"
    assert policy.path_in_scope_rule.action == "allow"
    assert policy.path_out_of_scope_rule.action == "ask"
    assert policy.path_out_of_scope_rule.fallback_action == "deny"
    assert policy.command_allowed_rule.action == "allow"
    assert policy.command_disallowed_rule.action == "ask"
    assert policy.command_disallowed_rule.fallback_action == "deny"


def test_tool_access_rule_and_policy_are_frozen():
    """ToolAccessRule / ToolAccessPolicy 为 frozen dataclass，属性赋值必须抛 FrozenInstanceError。"""
    # Arrange
    rule = ToolAccessRule(action="allow")
    policy = ToolAccessPolicy()

    # Act / Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.action = "deny"
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.default_rule = ToolAccessRule(action="deny")


def test_tool_guard_context_defaults_and_frozen():
    """ToolGuardContext 默认值必须为空且不可变，避免各工具共享可变状态。"""
    # Arrange
    context = ToolGuardContext()

    # Act / Assert
    assert context.cwd is None
    assert context.allowed_paths == []
    assert context.allowed_commands == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.cwd = Path(".")

    # 可变字段默认值必须互不共享（field(default_factory=list)）
    another = ToolGuardContext()
    context.allowed_paths.append(Path("x"))
    assert another.allowed_paths == []


def test_message_typed_dict_supports_tool_calls_and_extensions():
    """Message 模型必须承载 tool_calls（含 type='function'）与 extensions/usage 等完整字段。"""
    # Arrange
    message: Message = {
        "role": "assistant",
        "content": "hi",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
            }
        ],
        "extensions": {"usage": {"input_tokens": 10, "output_tokens": 5}},
    }
    tool_result: Message = {
        "role": "tool",
        "content": "hello",
        "tool_call_id": "call_1",
    }

    # Act / Assert
    assert message["tool_calls"][0]["type"] == "function"
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert message["extensions"]["usage"]["input_tokens"] == 10
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == "call_1"


def test_chat_chunk_defaults_and_fields():
    """ChatChunk 默认值必须为空字符串/None，且可承载 delta 与最终消息。"""
    # Arrange
    empty = ChatChunk()

    # Act / Assert
    assert empty.delta == ""
    assert empty.reasoning_delta == ""
    assert empty.message is None
    assert empty.state is None

    # Arrange
    full = ChatChunk(delta="x", reasoning_delta="r", message={"role": "assistant", "content": "hi"})

    # Act / Assert
    assert full.delta == "x"
    assert full.reasoning_delta == "r"
    assert full.message["content"] == "hi"
