"""Keyless composition checks for real registration and trusted caller wiring."""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.invocation import CURRENT_HUMAN_MESSAGE, human_message_entry
from neobot_app.agent_tools.runtime import AgentToolRuntime
from neobot_app.agents.problem_solver import ProblemSolverAgent, ProblemSolverManager, _TOOL_CONTEXT
from neobot_app.config.schemas.bot import AgentToolsConfig
from neobot_app.credentials.service import CredentialManager
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.skills import build_all_skills
from neobot_app.skills.agent_tools_skill import AgentToolsSkill
from neobot_app.skills.base import SkillManager


class Provider:
    model = "mock"
    max_tokens = 1000

    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.seen = []

    async def chat(self, messages, tools=None):
        self.seen.append((list(messages), tools))
        return self.replies.pop(0) if self.replies else {"role": "assistant", "content": "done"}

    async def close(self):
        pass


def tool_call(name, arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": "call1", "type": "function",
              "function": {"name": name, "arguments": json.dumps(arguments)}}]}


async def test_build_all_skills_attaches_solver_and_declares_real_tools(tmp_path):
    provider = Provider()
    sandbox = SandboxService(tmp_path / "sandbox")
    manager = ProblemSolverManager()
    solver = ProblemSolverAgent(provider, manager=manager, sandbox_service=sandbox)
    manager.set_agent(solver)
    skills = build_all_skills(sandbox_service=sandbox, problem_solver_manager=manager,
                              agent_provider=provider, data_dir=tmp_path)
    shared = skills.get("agent_tools")
    assert isinstance(shared, AgentToolsSkill)
    names = {d["function"]["name"] for d in skills.get_tools()}
    assert shared.runtime.config.mode == "native"
    assert {"agent_tools__read", "agent_tools__job_output", "agent_tools__todo_write",
            "agent_tools__lsp", "agent_tools__web_search", "agent_tools__web_fetch"} <= names
    assert not {"agent_tools__run_code", "agent_tools__subagent_fork", "agent_tools__ralph",
                "agent_tools__session_event_search", "agent_tools__terminal_open",
                "agent_tools__create_goal", "agent_tools__execute_command"} & names
    solver_names = {d["function"]["name"] for d in solver.tool_definitions}
    assert {"read", "edit", "grep", "lsp", "web_search", "web_fetch",
            "get_chat_context", "submit_solution"} <= solver_names
    assert not {"run_code", "search", "read_page", "search_status", "write_file",
                "read_file", "parse_image", "execute_command"} & solver_names
    await manager.shutdown()
    await shared.close()


async def test_main_ptc_file_sequence_uses_real_registry(tmp_path):
    sandbox = SandboxService(tmp_path / "sandbox")
    runtime = AgentToolRuntime(sandbox, state_dir=tmp_path / "state", config=AgentToolsConfig(mode="ptc"))
    skills = SkillManager()
    skills.register(AgentToolsSkill(runtime))
    executor = ReplyToolExecutor(skill_manager=skills, conv_kind="group", conv_id="123", current_user_id=7, human_request=True)
    try:
        result = json.loads(await executor.execute("agent_tools__run_code", {
            "description": "Create and inspect a file",
            "code": 'await tools.write({"file_path": "hello.txt", "content": "你好"})\nr = await tools.read({"file_path": "hello.txt"})\nreturn r["content"]',
            "_owner": "foreign", "pipeline_key": "group:999",
        }))
        assert result["result"] == "你好"
        assert (sandbox.get_temp_dir("group:123") / "hello.txt").read_text(encoding="utf-8") == "你好"
        assert not sandbox.get_temp_dir("group:999").exists()
    finally:
        await executor.close()
        await runtime.close()


async def test_solver_ptc_wire_rejects_direct_native_and_uses_structured_context(tmp_path):
    provider = Provider([tool_call("write", {"file_path": "no.txt", "content": "no"})])
    runtime = AgentToolRuntime(SandboxService(tmp_path / "sandbox"), state_dir=tmp_path / "state", config=AgentToolsConfig(mode="ptc"))
    solver = ProblemSolverAgent(provider)
    solver.set_tool_runtime(runtime)
    context = ToolContext("group:123:solver", "group:123", agent_id="solver", parent_agent_id="main")
    try:
        result = await solver._invoke_direct({"messages": [{"role": "user", "content": "task"}],
            "_agent_tool_context": context, "_chat_flow_id": "group:123",
            "_delegate_context": "[当前会话]\nkind=group\nid=999"})
        assert [d["function"]["name"] for d in provider.seen[0][1]] == ["run_code"]
        assert any("denied" in m.get("content", "") for m in result["messages"] if m["role"] == "tool")
        assert not (runtime.workspace(context) / "no.txt").exists()
        assert _TOOL_CONTEXT.get() is None
    finally:
        await solver.close()
        await runtime.close()


async def test_human_provenance_entry_does_not_leak_to_notices():
    class Entry:
        @human_message_entry
        async def handle(self, event):
            return CURRENT_HUMAN_MESSAGE.get()
    entry = Entry()
    assert await entry.handle({"post_type": "message", "message_type": "group", "user_id": 1, "self_id": 2}) is True
    assert await entry.handle({"post_type": "notice", "message_type": "group", "user_id": 1, "self_id": 2}) is False
    assert await entry.handle({"post_type": "message", "message_type": "group", "user_id": 2, "self_id": 2}) is False
    assert CURRENT_HUMAN_MESSAGE.get() is False


async def test_question_real_answer_and_cross_user_rejection(tmp_path):
    runtime = AgentToolRuntime(SandboxService(tmp_path / "sandbox"), state_dir=tmp_path / "state",
                               config=AgentToolsConfig(mode="native"))
    context = ToolContext("group:123:main", "group:123", user_id=7, human_request=True)
    try:
        question = await runtime.execute("ask_user_question", {"questions": [{"id": "q", "question": "Which format?"}]}, context)
        command = f'/agent-answer {question["question_id"]} PDF'
        rejected = await runtime.accept_human_input(replace(context, user_id=8), command, "msg1")
        assert "未接受" in rejected
        assert "已记录" in await runtime.accept_human_input(context, command, "msg2")
        status = await runtime.execute("question_status", {"question_id": question["question_id"]}, context)
        assert status["status"] == "answered"
    finally:
        await runtime.close()


async def test_goal_ptc_completion_has_real_round_authority(tmp_path):
    credentials = CredentialManager(SimpleNamespace(can=lambda *_: True))
    context = ToolContext("group:123:main", "group:123", user_id=7, human_request=True)
    code = ('g = await tools.get_goal({})\n'
            'return await tools.update_goal({"goal_id": g["goal"]["goal_id"], "revision": g["goal"]["revision"], "action": "complete"})')
    provider = Provider([tool_call("run_code", {"code": code, "description": "Complete this goal"})])
    runtime = AgentToolRuntime(SandboxService(tmp_path / "sandbox"), state_dir=tmp_path / "state",
                               credential_manager=credentials, provider=provider, config=AgentToolsConfig(mode="ptc"))
    try:
        credential = credentials.create(chat_flow=context.chat_flow_id, action="agent_goal", requester_id=7, cred_type="one_time")
        credentials.try_issue(chat_flow=context.chat_flow_id, code=credential.code, issuer_id=7)
        created = (await runtime.execute("run_code", {"description": "Create approved goal",
            "code": 'return await tools.create_goal({"objective": "Check calculation", "max_goal_rounds": 2})'}, context))["result"]
        with pytest.raises(AgentToolError, match="matching live goal round"):
            await runtime.execute("run_code", {"description": "Reject untrusted completion", "code":
                "return await tools.update_goal(" + json.dumps({"goal_id": created["goal"]["goal_id"],
                    "revision": created["goal"]["revision"], "action": "complete"}) + ")"},
                replace(context, human_request=False))
        runtime.finish_turn(context, [{"role": "user", "content": "Check calculation"}])
        await runtime.goals.wait(context)
        result = (await runtime.execute("run_code", {"description": "Inspect goal state",
            "code": "return await tools.get_goal({})"}, context))["result"]
        assert result["goal"]["phase"] == "complete"
        assert result["goal"]["rounds_started"] == 1
    finally:
        await runtime.close()


async def test_goal_runs_after_approved_root_turn_and_stops_at_budget(tmp_path):
    credentials = CredentialManager(SimpleNamespace(can=lambda *_: True))
    context = ToolContext("group:123:main", "group:123", user_id=7, human_request=True)
    runtime = AgentToolRuntime(SandboxService(tmp_path / "sandbox"), state_dir=tmp_path / "state",
                               credential_manager=credentials, provider=Provider(), config=AgentToolsConfig(mode="ptc"))
    try:
        with pytest.raises(AgentToolError, match="凭据"):
            await runtime.execute("run_code", {"description": "Request goal without credential",
                "code": 'return await tools.create_goal({"objective": "Check calculation"})'}, context)
        credential = credentials.create(chat_flow=context.chat_flow_id, action="agent_goal", requester_id=7, cred_type="one_time")
        credentials.try_issue(chat_flow=context.chat_flow_id, code=credential.code, issuer_id=7)
        await runtime.execute("run_code", {"description": "Create bounded approved goal",
            "code": 'return await tools.create_goal({"objective": "Check calculation", "max_goal_rounds": 1})'}, context)
        runtime.finish_turn(context, [{"role": "user", "content": "Check calculation"}])
        await runtime.goals.wait(context)
        result = (await runtime.execute("run_code", {"description": "Inspect goal state",
            "code": "return await tools.get_goal({})"}, context))["result"]
        assert result["goal"]["rounds_started"] == 1
        assert result["activation"] == "disarmed"
        assert not runtime.goals.is_running_round(replace(context, human_request=False))
    finally:
        await runtime.close()
