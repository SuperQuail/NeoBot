"""Compact native transport and isolated PTC capabilities, without network/LLM calls."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.runtime import AgentToolRuntime
from neobot_app.config.schemas.bot import AgentToolsConfig


BASIC = {"read", "write", "edit", "glob", "grep", "read_image", "lsp",
         "run_python", "pwsh" if os.name == "nt" else "bash", "web_search", "web_fetch",
         "job_list", "job_output", "job_kill", "todo_write", "ask_user_question",
         "question_status", "enter_plan_mode", "exit_plan_mode", "skill"}
ADVANCED = {"terminal_open", "terminal_send", "terminal_read", "terminal_signal",
            "terminal_list", "terminal_close", "create_goal", "get_goal", "update_goal",
            "subagent", "subagent_fork", "list_agents", "send_message", "interrupt_agent",
            "subagent_result", "workflow", "ralph", "session_search", "session_event_read",
            "session_event_search", "session_event_trace", "session_trace"}


def names(definitions):
    return {definition["function"]["name"] for definition in definitions}


def ptc(code):
    return {"code": code, "description": "Check selected tool mode"}


@pytest.fixture
async def runtime(tmp_path, make_sandbox, request):
    instance = AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "mode-state",
        config=AgentToolsConfig(mode=getattr(request, "param", "native")),
        provider=SimpleNamespace(), vision_provider=SimpleNamespace())
    yield instance
    await instance.close()


@pytest.fixture
def context():
    return ToolContext("group:123:main", "group:123", user_id=7, human_request=True)


def test_config_defaults_keep_ptc_available_without_selecting_it():
    config = AgentToolsConfig()
    assert config.mode == "native"
    assert config.ptc_enabled is True
    assert config.lsp_enabled is True
    assert config.lsp_servers == {}


async def test_native_wire_is_strictly_smaller_than_available_capabilities(runtime):
    wire = names(runtime.definitions())
    leaves = names(runtime.capability_definitions())
    assert wire == BASIC
    assert ADVANCED <= leaves
    assert not ADVANCED & wire
    assert len(wire) <= 20
    assert len(leaves) >= len(wire) + len(ADVANCED)
    assert "execute_command" not in leaves | wire
    assert "run_code" not in leaves | wire
    assert runtime.capability_names() == leaves
    assert all(runtime.is_wire_tool(name) for name in wire)
    assert not any(runtime.is_wire_tool(name) for name in ADVANCED | {"run_code"})


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
async def test_definitions_choose_presentation_without_changing_execution_mode(runtime):
    assert names(runtime.definitions(mode="native")) == BASIC
    assert names(runtime.definitions(mode="ptc")) == {"run_code"}
    assert names(runtime.definitions()) == (BASIC if runtime.config.mode == "native" else {"run_code"})
    assert names(runtime.capability_definitions()) >= BASIC | ADVANCED
    # Returned schemas are detached snapshots, not writable registry authority.
    definitions = runtime.capability_definitions()
    definitions[0]["function"]["name"] = "forged"
    assert "forged" not in runtime.capability_names()


@pytest.mark.parametrize("name", sorted(ADVANCED | {"run_code", "execute_command"}))
async def test_native_rejects_programmatic_and_advanced_direct_calls(runtime, context, name):
    with pytest.raises(AgentToolError) as error:
        await runtime.execute(name, ptc("return 7") if name == "run_code" else {}, context)
    assert error.value.code == "MODE_TOOL_DENIED"


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_rejects_every_direct_leaf_even_when_explicitly_allowlisted(runtime, context):
    context = replace(context, allowed_tools=runtime.capability_names() | {"run_code"})
    assert names(runtime.definitions()) == {"run_code"}
    for name in runtime.capability_names():
        with pytest.raises(AgentToolError) as error:
            await runtime.execute(name, {}, context)
        assert error.value.code == "MODE_TOOL_DENIED", name


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
async def test_basic_file_roundtrip_uses_selected_transport(runtime, context):
    if runtime.config.mode == "native":
        await runtime.execute("write", {"file_path": "mode.txt", "content": "native"}, context)
        result = await runtime.execute("read", {"file_path": "mode.txt"}, context)
        assert result["content"] == "native"
    else:
        result = await runtime.execute("run_code", ptc(
            'await tools.write({"file_path": "mode.txt", "content": "ptc"})\n'
            'return await tools.read({"file_path": "mode.txt"})'), context)
        assert result["result"]["content"] == "ptc"


@pytest.mark.parametrize("runtime", ["native", "ptc"], indirect=True)
async def test_mode_does_not_expand_inherited_leaf_acl(runtime, context):
    context = replace(context, allowed_tools=frozenset({"run_code", "read"}))
    with pytest.raises(AgentToolError) as error:
        if runtime.config.mode == "native":
            await runtime.execute("write", {"file_path": "forbidden.txt", "content": "no"}, context)
        else:
            await runtime.execute("run_code", ptc(
                'return await tools.write({"file_path": "forbidden.txt", "content": "no"})'), context)
    assert error.value.code == ("TOOL_DENIED" if runtime.config.mode == "native" else "PTC_TOOL_DENIED")
    assert not (runtime.workspace(context) / "forbidden.txt").exists()
    assert names(runtime.definitions(mode="native", allowed_tools=context.allowed_tools)) == {"read"}
    assert names(runtime.capability_definitions(allowed_tools=context.allowed_tools)) == {"read"}


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_transport_itself_requires_acl_permission(runtime, context):
    context = replace(context, allowed_tools=frozenset({"read"}))
    assert runtime.definitions(allowed_tools=context.allowed_tools) == []
    with pytest.raises(AgentToolError) as error:
        await runtime.execute("run_code", ptc("return 7"), context)
    assert error.value.code == "TOOL_DENIED"


@pytest.mark.parametrize("runtime", ["ptc"], indirect=True)
async def test_ptc_schema_does_not_expose_host_authority(runtime, context):
    schema = runtime.definitions()[0]["function"]["parameters"]
    assert set(schema["properties"]) == {"code", "description"}
    assert "_program_dispatch" not in json.dumps(runtime.definitions())
    # A JSON lookalike is not the private identity token used by the host.
    with pytest.raises(AgentToolError) as error:
        await runtime.execute("write", {"file_path": "forged.txt", "content": "no",
            "_program_dispatch": True}, context, _program_dispatch=True)
    assert error.value.code == "MODE_TOOL_DENIED"
    assert not (runtime.workspace(context) / "forged.txt").exists()


@pytest.mark.parametrize("mode, enabled", [("invalid", True), ("ptc", False)])
def test_invalid_mode_configuration_fails_before_runtime_start(tmp_path, make_sandbox, mode, enabled):
    with pytest.raises(ValueError):
        AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "invalid-state",
            config=AgentToolsConfig(mode=mode, ptc_enabled=enabled))
    assert not (tmp_path / "invalid-state").exists()


@pytest.mark.parametrize("enabled", [False, True])
async def test_legacy_both_migrates_to_compact_native_without_startup_failure(tmp_path, make_sandbox, enabled):
    with pytest.warns(FutureWarning, match="compact native"):
        runtime = AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "legacy-state",
            config=AgentToolsConfig(mode="both", ptc_enabled=enabled))
    try:
        assert runtime.mode == "native"
        assert "run_code" not in names(runtime.definitions())
        assert not names(runtime.definitions()) & ADVANCED
    finally:
        await runtime.close()


async def test_disabling_ptc_preserves_native_tools_and_rejects_ptc_preview(tmp_path, make_sandbox):
    runtime = AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "state",
        config=AgentToolsConfig(mode="native", ptc_enabled=False))
    try:
        assert {"read", "write", "lsp", "web_search"} <= names(runtime.definitions())
        with pytest.raises(ValueError):
            runtime.definitions(mode="ptc")
    finally:
        await runtime.close()


async def test_empty_lsp_mapping_retains_lazy_default_python_servers(runtime):
    assert "lsp" in names(runtime.definitions())
    assert set(runtime.lsp._servers) == {".py", ".pyi"}
    for command, language in runtime.lsp._servers.values():
        assert command == [sys.executable, "-I", "-m", "pylsp"]
        assert language == "python"
    assert runtime.lsp._clients == {}


@pytest.mark.parametrize("enabled", [False, True])
async def test_lsp_override_merges_defaults_or_explicit_disable_wins(tmp_path, make_sandbox, enabled):
    override = {".py": {"command": [sys.executable, "-m", "custom_lsp"], "language_id": "python"},
                ".rs": {"command": [sys.executable, "-m", "rust_lsp"], "language_id": "rust"}}
    config = AgentToolsConfig(mode="native", lsp_enabled=enabled, lsp_servers=override)
    runtime = AgentToolRuntime(make_sandbox(), state_dir=tmp_path / "state", config=config)
    try:
        assert ("lsp" in names(runtime.definitions())) is enabled
        assert ("lsp" in runtime.capability_names()) is enabled
        if enabled:
            assert set(runtime.lsp._servers) == {".py", ".pyi", ".rs"}
            assert runtime.lsp._servers[".py"][0][-1] == "custom_lsp"
            assert runtime.lsp._servers[".pyi"][0][-1] == "pylsp"
            assert runtime.lsp._servers[".rs"][1] == "rust"
            assert ".pyi" not in config.lsp_servers
        else:
            assert runtime.lsp._servers == {}
    finally:
        await runtime.close()
