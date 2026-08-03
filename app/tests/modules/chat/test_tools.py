from __future__ import annotations

from pathlib import Path

import pytest

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.types import ToolAccessPolicy, ToolGuardContext
from neobot_chat.tools.builtin import build_builtin_toolset
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.tools.toolset import ToolSpec, Toolset


class _FakeAgent:
    """注册表最小可用子 Agent（仅需 description 即可 list）。"""

    description = "fake agent"

    async def invoke(self, state: dict) -> dict:
        return state

    async def close(self) -> None:
        return None

    def definitions(self) -> list:
        return []


def _tool_def(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"type": "object"}},
    }


def _allow_resolver(args: dict, context: ToolGuardContext, policy: ToolAccessPolicy):
    return policy.default_rule


class _FakeExecutor:
    """按名字清单提供定义、带前缀返回执行结果的假执行器。"""

    def __init__(self, prefix: str, names: list[str]) -> None:
        self._prefix = prefix
        self._names = list(names)

    def definitions(self) -> list[dict]:
        return [_tool_def(name) for name in self._names]

    async def execute(self, name: str, args: dict) -> str:
        return f"{self._prefix}:{name}"

    async def close(self) -> None:
        return None


async def test_builtin_toolset_defines_expected_tools_with_schemas(tmp_path: Path):
    """带 AgentRegistry 时工具集必须包含 6 个内置工具，且 JSON Schema 的必填参数正确。"""
    # Arrange
    registry = AgentRegistry()
    registry.register("helper", _FakeAgent())
    toolset = build_builtin_toolset(cwd=tmp_path, agent_registry=registry)

    # Act
    by_name = {spec.name: spec for spec in toolset.specs}

    # Assert
    assert set(by_name) == {
        "read_file",
        "write_file",
        "list_files",
        "execute_command",
        "list_agents",
        "delegate",
    }
    read_params = by_name["read_file"].definition["function"]["parameters"]
    assert read_params["required"] == ["path"]
    write_params = by_name["write_file"].definition["function"]["parameters"]
    assert write_params["required"] == ["path", "content"]
    exec_params = by_name["execute_command"].definition["function"]["parameters"]
    assert exec_params["required"] == ["command"]
    delegate_params = by_name["delegate"].definition["function"]["parameters"]
    assert delegate_params["properties"]["tasks"]["items"]["required"] == ["agent", "task"]


async def test_builtin_execute_unknown_tool_raises_tool_error(tmp_path: Path):
    """执行未注册的工具名必须抛出 ToolError 而不是静默返回。"""
    # Arrange
    toolset = build_builtin_toolset(cwd=tmp_path)

    # Act / Assert
    with pytest.raises(ToolError, match="Unknown tool: ghost_tool"):
        await toolset.executor.execute("ghost_tool", {})
    await toolset.executor.close()


async def test_builtin_read_write_list_files_roundtrip(tmp_path: Path):
    """write_file 写入后 read_file 必须读回相同内容，list_files 必须列出该文件。"""
    # Arrange
    toolset = build_builtin_toolset(cwd=tmp_path)

    # Act
    write_result = await toolset.executor.execute(
        "write_file", {"path": "sub/data.txt", "content": "hello"}
    )
    read_result = await toolset.executor.execute("read_file", {"path": "sub/data.txt"})
    list_result = await toolset.executor.execute("list_files", {"path": "."})

    # Assert
    assert "Successfully wrote" in write_result
    assert read_result == "hello"
    assert (tmp_path / "sub" / "data.txt").read_text(encoding="utf-8") == "hello"
    assert "sub" in list_result

    await toolset.executor.close()


@pytest.mark.xfail(
    reason="BUG-0103 BuiltinTools.execute 缺少必需参数时泄漏 TypeError 而非抛出 ToolError",
    strict=False,
)
async def test_builtin_execute_validates_missing_required_param(tmp_path: Path):
    """read_file 缺 path 参数时 execute 必须抛出明确的 ToolError 进行参数校验。"""
    # Arrange
    toolset = build_builtin_toolset(cwd=tmp_path)

    # Act / Assert
    with pytest.raises(ToolError):
        await toolset.executor.execute("read_file", {})
    await toolset.executor.close()


async def test_path_resolver_allows_in_scope_and_asks_out_of_scope(tmp_path: Path):
    """路径在 allowed_paths 内必须放行，在外必须返回 ask/deny 规则。"""
    # Arrange
    toolset = build_builtin_toolset(cwd=tmp_path)
    spec = next(s for s in toolset.specs if s.name == "read_file")
    policy = ToolAccessPolicy()
    in_scope_ctx = ToolGuardContext(cwd=tmp_path, allowed_paths=[tmp_path])
    out_scope_ctx = ToolGuardContext(
        cwd=tmp_path, allowed_paths=[tmp_path]
    )
    outside = tmp_path.parent / "outside.txt"

    # Act
    rule_in = spec.access_resolver({"path": "inner.txt"}, in_scope_ctx, policy)
    rule_out = spec.access_resolver({"path": str(outside)}, out_scope_ctx, policy)

    # Assert
    assert rule_in.action == "allow"
    assert rule_out.action == "ask"
    assert rule_out.fallback_action == "deny"


async def test_command_resolver_allows_only_whitelisted_commands(tmp_path: Path):
    """命令首词命中 allowed_commands 时放行，未命中或白名单为空时必须拒绝。"""
    # Arrange
    toolset = build_builtin_toolset(cwd=tmp_path, allowed_commands=["python", "dir"])
    spec = next(s for s in toolset.specs if s.name == "execute_command")
    policy = ToolAccessPolicy()
    allowed_ctx = ToolGuardContext(cwd=tmp_path, allowed_commands=["python", "dir"])
    empty_ctx = ToolGuardContext(cwd=tmp_path, allowed_commands=[])

    # Act
    rule_ok = spec.access_resolver({"command": "python script.py"}, allowed_ctx, policy)
    rule_bad = spec.access_resolver({"command": "rm -rf /"}, allowed_ctx, policy)
    rule_no_whitelist = spec.access_resolver(
        {"command": "python script.py"}, empty_ctx, policy
    )

    # Assert
    assert rule_ok.action == "allow"
    assert rule_bad.action == "ask"
    assert rule_bad.fallback_action == "deny"
    assert rule_no_whitelist.action == "ask"


async def test_toolset_merge_prefers_later_duplicate_and_routes_execution():
    """重名工具合并时必须去重且优先取后一个 toolset 的定义，执行须路由到归属执行器。"""
    # Arrange
    exec_a = _FakeExecutor("A", ["dup", "a"])
    exec_b = _FakeExecutor("B", ["dup", "b"])
    toolset_a = Toolset(
        executor=exec_a,
        specs=[ToolSpec(_tool_def("dup"), _allow_resolver), ToolSpec(_tool_def("a"), _allow_resolver)],
    )
    toolset_b = Toolset(
        executor=exec_b,
        specs=[ToolSpec(_tool_def("dup"), _allow_resolver), ToolSpec(_tool_def("b"), _allow_resolver)],
    )

    # Act
    merged = Toolset.merge([toolset_a, toolset_b])
    names = [spec.name for spec in merged.specs]
    dup_spec = next(spec for spec in merged.specs if spec.name == "dup")
    result = await merged.executor.execute("dup", {})

    # Assert
    assert set(names) == {"dup", "a", "b"}
    assert names.count("dup") == 1
    assert dup_spec is toolset_b.specs[0]
    assert result == "B:dup"
    await merged.executor.close()


async def test_toolset_merge_with_all_none_returns_empty_toolset():
    """全部 toolset 为 None 时 merge 必须返回空 Toolset 且不抛错。"""
    # Arrange / Act
    merged = Toolset.merge([None, None])

    # Assert
    assert merged.specs == []
    assert merged.definitions() == []
