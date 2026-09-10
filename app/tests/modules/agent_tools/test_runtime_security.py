"""Strict shared-runtime security regressions; only synthetic data and temp files."""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from jsonschema import Draft202012Validator

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext, tool_definition
from neobot_app.agent_tools.runtime import AgentToolRuntime, result_json
from neobot_app.config.schemas.bot import AgentToolsConfig
from neobot_app.skills.agent_tools_skill import AgentToolsSkill
from neobot_app.skills.base import SkillManager, SkillModule


@pytest.fixture
async def runtime(tmp_path, make_sandbox, request):
    runtime = AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "agent-state",
        config=AgentToolsConfig(mode=getattr(request, "param", "native"), web_enabled=False))
    yield runtime
    await runtime.close()


def context(**changes):
    return replace(ToolContext(owner="group:123:main", chat_flow_id="group:123",
                               user_id=123, human_request=True), **changes)


def ptc(code):
    return {"code": code, "description": "Security regression"}


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_published_ptc_schema_matches_required_invocation(runtime):
    definition = next(d for d in runtime.definitions() if d["function"]["name"] == "run_code")
    args = ptc("return 7")
    Draft202012Validator(definition["function"]["parameters"]).validate(args)
    assert (await runtime.execute("run_code", args, context()))["result"] == 7


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_does_not_expand_native_allowlist(runtime):
    ctx = context(allowed_tools=frozenset({"run_code", "read"}))
    with pytest.raises(AgentToolError):
        await runtime.execute("run_code", ptc(
            'return await tools.write({"file_path": "forbidden.txt", "content": "no"})'), ctx)
    assert not (runtime.workspace(ctx) / "forbidden.txt").exists()


@pytest.mark.parametrize("runtime, programmatic", [("native", False), ("ptc", True)], indirect=["runtime"])
async def test_credentials_gate_native_and_ptc_before_process_start(runtime, monkeypatch, programmatic):
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(runtime.processes, "execute", execute)
    with pytest.raises(AgentToolError) as error:
        if programmatic:
            await runtime.execute("run_code", ptc(
                'return await tools.run_python({"code": "print(1)"})'), context())
        else:
            await runtime.execute("run_python", {"code": "print(1)"}, context())
    assert error.value.code == "CREDENTIAL_REQUIRED"
    execute.assert_not_awaited()


async def test_plan_blocks_execution_before_consuming_credential(runtime, monkeypatch):
    await runtime.execute("enter_plan_mode", {}, context())
    consume = Mock(return_value=object())
    runtime.permissions.manager = SimpleNamespace(consume=consume)
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(runtime.processes, "execute", execute)
    with pytest.raises(AgentToolError) as error:
        await runtime.execute("run_python", {"code": "print(1)"}, context())
    assert error.value.code == "PLAN_MODE"
    consume.assert_not_called()
    execute.assert_not_awaited()


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_goal_cannot_inherit_human_authority(runtime):
    consume = Mock(return_value=object())
    runtime.permissions.manager = SimpleNamespace(consume=consume)
    with pytest.raises(AgentToolError) as error:
        await runtime.execute("run_code", ptc(
            'return await tools.create_goal({"objective": "child must not arm"})'),
                              context(agent_id="child", parent_agent_id="main", depth=1, human_request=False))
    assert error.value.code == "HUMAN_REQUIRED"
    consume.assert_not_called()


async def test_shared_write_requires_current_chat_credential(runtime):
    with pytest.raises(AgentToolError) as error:
        await runtime.execute("write", {"file_path": "shared:tools/new.txt", "content": "test"}, context())
    assert error.value.code == "CREDENTIAL_REQUIRED"


def test_nested_module_errors_preserve_stable_code_and_message():
    with pytest.raises(AgentToolError) as error:
        result_json({"ok": False, "error": {"code": "lsp_timeout", "message": "bounded failure"}})
    assert error.value.code == "lsp_timeout"
    assert str(error.value) == "bounded failure"


def test_legacy_skill_manager_failure_is_not_successful_content():
    with pytest.raises(AgentToolError):
        result_json("工具执行失败 [fake__test]")


class _FakeSkill(SkillModule):
    def __init__(self, name, local, value=None):
        self._name, self.local, self.value = name, local, value
        self.calls = []

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "Synthetic security fixture"

    def get_tools(self):
        return [tool_definition(self.local, "Synthetic test")]

    async def execute(self, name, args):
        self.calls.append((name, args))
        return self.value if self.value is not None else json.dumps({"ok": True})


def reply_executor(runtime, skill, **kwargs):
    from neobot_app.reply.tools import ReplyToolExecutor

    manager = SkillManager()
    manager.register(AgentToolsSkill(runtime))
    manager.register(skill)
    runtime.skill_manager = manager
    return ReplyToolExecutor(skill_manager=manager, conv_kind="group", conv_id="123",
                             current_user_id=123, human_request=True, **kwargs)


@pytest.mark.parametrize("name, local", [("sandbox_manager", "write_file_base64"),
    ("background_trigger", "submit_problem"), ("agents", "delegate")])
async def test_native_legacy_mutation_and_delegation_cannot_bypass_plan(runtime, name, local):
    skill = _FakeSkill(name, local)
    executor = reply_executor(runtime, skill)
    try:
        await runtime.execute("enter_plan_mode", {}, context())
        result = json.loads(await executor.execute(f"{name}__{local}", {}))
        assert result.get("ok") is False, result
        assert result.get("code") == "PLAN_MODE", result
        assert skill.calls == []
    finally:
        await executor.close()


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_external_dispatch_preserves_out_of_band_image_parts(runtime):
    """任务型 Agent 的 PTC 程序经宿主 dispatch 调外部技能工具时，带外图片必须穿过桥接层。

    主回复管线不再提供 run_code（PTC 只服务任务型 Agent），因此这里直接验证
    宿主桥接层本身：dispatch 收到的 ImageContextResult.image_parts 不能丢。
    """
    from neobot_app.skills.image_context_skill import ImageContextResult

    parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,TEST"}}]
    skill = _FakeSkill("image_context", "add_image", ImageContextResult(
        json.dumps({"ok": True, "count": 1}), parts))
    collected: list[dict] = []

    async def dispatch(name, args):
        result = await skill.execute("add_image", args)
        collected.extend(getattr(result, "image_parts", []))
        return result

    definition = tool_definition(
        "image_context__add_image", "external image tool",
        {"type": "object", "properties": {}, "required": []}, [])
    result = await runtime.execute(
        "run_code",
        ptc("return await tools.image_context__add_image({})"),
        context(),
        external_dispatch=dispatch,
        external_definitions=[definition],
    )
    assert result["result"]["ok"] is True, result
    assert collected == parts
    assert len(skill.calls) == 1


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
@pytest.mark.parametrize("local", ["read_file", "write_file", "edit_file", "glob_files", "grep_files"])
async def test_reply_hides_and_rejects_duplicate_file_aliases(runtime, local):
    skill = _FakeSkill("sandbox_manager", local)
    executor = reply_executor(runtime, skill)
    name = f"sandbox_manager__{local}"
    try:
        assert name not in {d["function"]["name"] for d in executor.definitions()}
        assert not executor.is_tool_authorized(name)
        assert "Error:" in await executor.execute(name, {})
        assert skill.calls == []
    finally:
        await executor.close()


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
@pytest.mark.parametrize("name, local", [("sandbox_manager", "list_files"),
    ("sandbox_manager", "write_file_base64"), ("sandbox_manager", "send_file"),
    ("sandbox_manager", "download_file"), ("image_context", "add_image")])
async def test_reply_keeps_native_chat_image_and_file_delivery_business(runtime, name, local):
    skill = _FakeSkill(name, local)
    executor = reply_executor(runtime, skill, native_vision_provider=SimpleNamespace(native_vision=True))
    try:
        names = {d["function"]["name"] for d in executor.definitions()}
        assert {"send_reply", f"{name}__{local}"} <= names
        assert executor.is_tool_authorized(f"{name}__{local}")
        # 主回复管线的任务工具呈现与 native/PTC 无关：始终是可直接调用的叶子工具，
        # 永远不暴露 PTC 的 run_code 入口（那是任务型 Agent 的编排能力）。
        task_names = {n for n in names if n.startswith("agent_tools__")}
        assert {"agent_tools__read", "agent_tools__todo_write"} <= task_names
        assert "agent_tools__run_code" not in task_names
    finally:
        await executor.close()


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
async def test_reply_never_exposes_run_code_and_keeps_leaf_allowlist(runtime):
    """PTC 不再改变主 Agent 的呈现；技能白名单对叶子工具仍然生效。"""
    executor = reply_executor(runtime, _FakeSkill("example", "read"),
        allowed_tools={"agent_tools__read"})
    try:
        names = {d["function"]["name"] for d in executor.definitions()}
        assert "agent_tools__run_code" not in names
        assert "agent_tools__read" in names
        assert "agent_tools__write" not in names
        assert executor.is_tool_authorized("agent_tools__read")
        assert not executor.is_tool_authorized("agent_tools__write")
        assert not executor.is_tool_authorized("agent_tools__run_code")

        # 白名单内的叶子工具仍可正常直接调用（宿主自决呈现，不受模式限制）
        await runtime.execute("write", {"file_path": "ok.txt", "content": "hi"},
                              context(), direct=True)
        result = await executor.execute("agent_tools__read", {"file_path": "ok.txt"})
        assert "hi" in result

        denied = await executor.execute(
            "agent_tools__write", {"file_path": "forbidden.txt", "content": "no"})
        assert "Error" in denied
        assert not (runtime.workspace(context()) / "forbidden.txt").exists()
    finally:
        await executor.close()


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_external_schema_validates_before_dispatch(runtime):
    dispatch = AsyncMock(return_value={"ok": True})
    definition = tool_definition("externalread", "test", {"path": {"type": "string"}}, ["path"])
    with pytest.raises(AgentToolError):
        await runtime.execute("run_code", ptc(
            'return await tools.externalread({"path": 42, "owner": "forged"})'), context(),
            external_dispatch=dispatch, external_definitions=[definition])
    dispatch.assert_not_awaited()


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_runtime_close_cancels_and_drains_active_ptc_before_state_close(runtime):
    started, finished = asyncio.Event(), asyncio.Event()

    async def dispatch(name, args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    task = asyncio.create_task(runtime.execute("run_code", ptc("return await tools.externalwait({})"),
        context(), external_dispatch=dispatch, external_definitions=[tool_definition("externalwait", "test")]))
    try:
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(runtime.close(), 3)
        assert finished.is_set()
        assert task.done()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
async def test_solver_removed_binary_alias_cannot_bypass_inherited_allowlist(runtime):
    from neobot_app.agents.problem_solver import ProblemSolverToolExecutor, _TOOL_CONTEXT

    executor = ProblemSolverToolExecutor(sandbox_service=runtime.sandbox)
    executor._runtime = runtime
    ctx = context(allowed_tools=frozenset({"read"}))
    marker = _TOOL_CONTEXT.set(ctx)
    try:
        result = json.loads(await executor.execute("write_file", {"path": "forbidden.bin",
            "content_base64": base64.b64encode(b"\xff\xfe\x00").decode("ascii")}))
        assert result.get("ok") is False, result
        assert result.get("code") == "TOOL_DENIED", result
        assert not (runtime.workspace(ctx) / "forbidden.bin").exists()
    finally:
        _TOOL_CONTEXT.reset(marker)
        await executor.close()
