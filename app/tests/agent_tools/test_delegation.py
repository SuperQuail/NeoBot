"""Dedicated ChildAgentTools tests; no network, Agent, or runtime dependencies."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.delegation import ChildAgentTools


ROOT = ToolContext(owner="owner-a", chat_flow_id="qq:123", user_id=42, human_request=True)


async def echo(context, messages):
    return [*messages, {"role": "assistant", "content": "reply:" + messages[-1]["content"]}]


@pytest.fixture
async def factory(tmp_path):
    instances = []

    def make(invoke=echo, **kwargs):
        state_dir = kwargs.pop("state_dir", tmp_path / str(len(instances)))
        instance = ChildAgentTools(state_dir, invoke, **kwargs)
        instances.append(instance)
        return instance

    yield make
    for instance in instances:
        await instance.close()


async def settled(service, agent_id):
    task = service._children[agent_id].runner
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 3)
    return await service.execute("subagent_result", {"agent_id": agent_id}, ROOT)


async def test_foreground_summary_context_and_definitions(factory):
    contexts, notifications = [], []

    async def invoke(context, messages):
        contexts.append(context)
        return [*messages, {"role": "assistant", "content": "old"},
                {"role": "tool", "content": "not summary"},
                {"role": "assistant", "content": [{"type": "text", "text": "last"}]}]

    service = factory(invoke, completion_callback=lambda parent, result: notifications.append((parent, result)))
    result = await service.execute("subagent", {"prompt": "task", "run_in_background": False}, ROOT)
    assert result["status"] == "idle" and result["outcome"] == "completed"
    assert result["summary"] == "last" and result["turns"] == 1
    child = contexts[0]
    assert child.owner != ROOT.owner and child.agent_id != ROOT.agent_id
    assert child.parent_agent_id == ROOT.agent_id and child.depth == 1
    assert child.chat_flow_id == ROOT.chat_flow_id and child.user_id == ROOT.user_id
    assert child.human_request is False
    assert notifications == [(ROOT, result)]
    definitions = {d["function"]["name"]: d["function"] for d in service.definitions()}
    assert set(definitions) == {"subagent", "subagent_fork", "list_agents", "send_message", "interrupt_agent", "subagent_result", "workflow", "ralph"}
    assert all(d["parameters"]["additionalProperties"] is False for d in definitions.values())


async def test_direct_parent_chat_owner_isolation_no_root_bypass(factory):
    service = factory()
    child = await service.execute("subagent", {"prompt": "child", "run_in_background": False}, ROOT)
    child_context = service._children[child["agent_id"]].context
    grandchild = await service.execute("subagent", {"prompt": "grandchild", "run_in_background": False}, child_context)
    strangers = [ROOT, replace(child_context, owner=ROOT.owner),
                 replace(child_context, chat_flow_id="qq:999"), replace(child_context, agent_id="other")]
    for caller in strangers:
        for tool, args in [("subagent_result", {}), ("interrupt_agent", {}), ("send_message", {"message": "x"})]:
            with pytest.raises(AgentToolError) as caught:
                await service.execute(tool, {"agent_id": grandchild["agent_id"], **args}, caller)
            assert caught.value.code == "permission_denied"
    listing = await service.execute("list_agents", {}, ROOT)
    assert [c["agent_id"] for c in listing["agents"]] == [child["agent_id"]]
    assert (await service.execute("list_agents", {}, replace(ROOT, owner="stranger")))["agents"] == []


async def test_allowlist_inherited_attenuated_and_recovered(factory, tmp_path):
    calls = []

    async def invoke(context, messages):
        calls.append(context)
        return await echo(context, messages)

    scope = frozenset({"subagent", "send_message", "subagent_result", "read"})
    root = replace(ROOT, allowed_tools=scope)
    service = factory(invoke, state_dir=tmp_path / "state")
    result = await service.execute("subagent", {"prompt": "first", "run_in_background": False}, root)
    assert calls[-1].allowed_tools == scope
    narrower = replace(ROOT, allowed_tools=frozenset({"send_message", "read"}))
    await service.execute("send_message", {"agent_id": result["agent_id"], "message": "second"}, narrower)
    await settled(service, result["agent_id"])
    assert calls[-1].allowed_tools == narrower.allowed_tools
    await service.execute("send_message", {"agent_id": result["agent_id"], "message": "third"}, ROOT)
    await settled(service, result["agent_id"])
    assert calls[-1].allowed_tools == narrower.allowed_tools
    with pytest.raises(AgentToolError, match="allowlist"):
        await service.execute("workflow", {"mode": "parallel", "steps": [{"prompt": "x"}]}, narrower)
    await service.close()
    restored = factory(invoke, state_dir=tmp_path / "state")
    assert restored._children[result["agent_id"]].context.allowed_tools == narrower.allowed_tools


async def test_queue_turn_order_no_concurrent_invoke(factory):
    started, release = asyncio.Event(), asyncio.Event()
    calls, active = [], 0

    async def invoke(context, messages):
        nonlocal active
        active += 1
        assert active == 1
        calls.append(messages)
        if len(calls) == 1:
            started.set()
            await release.wait()
        active -= 1
        return await echo(context, messages)

    service = factory(invoke)
    result = await service.execute("subagent", {"prompt": "one"}, ROOT)
    assert result["status"] == "running"
    await asyncio.wait_for(started.wait(), 3)
    for message in ["two", "three"]:
        await service.execute("send_message", {"agent_id": result["agent_id"], "message": message}, ROOT)
    assert len(calls) == 1
    release.set()
    result = await settled(service, result["agent_id"])
    assert [messages[-1]["content"] for messages in calls] == ["one", "two", "three"]
    assert [m["content"] for m in calls[-1]] == ["one", "reply:one", "two", "reply:two", "three"]
    assert result["turns"] == 3 and result["pending_messages"] == 0


async def test_interrupt_drains_cleanup_parks_queue_and_retains_session(factory):
    started, cleanup, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def invoke(context, messages):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release_cleanup.wait()
        return await echo(context, messages)

    service = factory(invoke)
    child = await service.execute("subagent", {"prompt": "one"}, ROOT)
    await asyncio.wait_for(started.wait(), 3)
    await service.execute("send_message", {"agent_id": child["agent_id"], "message": "two"}, ROOT)
    stopping = asyncio.create_task(service.execute("interrupt_agent", {"agent_id": child["agent_id"]}, ROOT))
    await asyncio.wait_for(cleanup.wait(), 3)
    assert not stopping.done()
    with pytest.raises(AgentToolError, match="interrupt"):
        await service.execute("send_message", {"agent_id": child["agent_id"], "message": "forbidden during drain"}, ROOT)
    release_cleanup.set()
    result = await asyncio.wait_for(stopping, 3)
    assert result["status"] == "idle" and result["outcome"] == "interrupted"
    assert result["pending_messages"] == 1 and calls == ["one"]
    await service.execute("send_message", {"agent_id": child["agent_id"], "message": "three"}, ROOT)
    await settled(service, child["agent_id"])
    assert calls == ["one", "two", "three"]


async def test_immediate_interrupt_before_runner_starts(factory):
    calls = []

    async def invoke(context, messages):
        calls.append(messages)
        return await echo(context, messages)

    service = factory(invoke)
    child = await service.execute("subagent", {"prompt": "one"}, ROOT)
    result = await service.execute("interrupt_agent", {"agent_id": child["agent_id"]}, ROOT)
    assert not calls
    assert result["outcome"] == "interrupted" and result["status"] == "idle"


async def test_foreground_cancellation_and_close_drain(factory):
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def invoke(context, messages):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    service = factory(invoke)
    task = asyncio.create_task(service.execute("subagent", {"prompt": "x", "run_in_background": False}, ROOT))
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    started.clear()
    cleaned.clear()
    child = await service.execute("subagent", {"prompt": "second"}, ROOT)
    await asyncio.wait_for(started.wait(), 3)
    await service.close()
    assert cleaned.is_set() and service._children[child["agent_id"]].runner.done()
    with pytest.raises(AgentToolError, match="closed"):
        await service.execute("list_agents", {}, ROOT)


async def test_restore_running_parks_history_and_pending_without_auto_invoke(factory, tmp_path):
    started = asyncio.Event()

    async def blocked(context, messages):
        started.set()
        await asyncio.Event().wait()

    original = factory(blocked)
    child = await original.execute("subagent", {"prompt": "inflight"}, ROOT)
    await asyncio.wait_for(started.wait(), 3)
    await original.execute("send_message", {"agent_id": child["agent_id"], "message": "queued"}, ROOT)
    saved = next(original.state_dir.glob("*.json")).read_bytes()
    await original.close()
    recovery_dir = tmp_path / "restart"
    recovery_dir.mkdir()
    name = hashlib.sha256(child["agent_id"].encode()).hexdigest() + ".json"
    (recovery_dir / name).write_bytes(saved)
    (recovery_dir / "malformed.json").write_text("not json")
    (recovery_dir / "oversized.json").write_bytes(b" " * 1_048_577)
    calls = []

    async def invoke(context, messages):
        calls.append(messages)
        return await echo(context, messages)

    restored = factory(invoke, state_dir=recovery_dir)
    result = await restored.execute("subagent_result", {"agent_id": child["agent_id"]}, ROOT)
    assert result["status"] == "idle" and result["outcome"] == "recovered"
    assert result["pending_messages"] == 1 and not calls
    assert restored._children[child["agent_id"]].runner is None
    assert len(restored.recovery_errors) == 2
    await restored.execute("send_message", {"agent_id": child["agent_id"], "message": "resume"}, ROOT)
    await settled(restored, child["agent_id"])
    assert [m[-1]["content"] for m in calls] == ["queued", "resume"]
    assert calls[0][0]["content"] == "inflight"
    assert not list(recovery_dir.glob("*.tmp"))


async def test_recovery_rejects_broader_child_acl(factory, tmp_path):
    root = replace(ROOT, allowed_tools=frozenset({"subagent"}))
    service = factory(state_dir=tmp_path / "state")
    child = await service.execute("subagent", {"prompt": "x", "run_in_background": False}, root)
    await service.close()
    path = next(service.state_dir.glob("*.json"))
    record = json.loads(path.read_text())
    record["context"]["allowed_tools"] = None
    path.write_text(json.dumps(record))
    recovered = factory(state_dir=service.state_dir)
    assert child["agent_id"] not in recovered._children and recovered.recovery_errors


async def test_depth_concurrency_session_queue_and_json_caps(factory):
    started = asyncio.Event()

    async def invoke(context, messages):
        started.set()
        await asyncio.Event().wait()

    service = factory(invoke, max_depth=1, max_children=1, max_pending=1, max_sessions=2)
    child = await service.execute("subagent", {"prompt": "x"}, ROOT)
    await asyncio.wait_for(started.wait(), 3)
    with pytest.raises(AgentToolError) as caught:
        await service.execute("subagent", {"prompt": "x"}, ROOT)
    assert caught.value.code == "child_limit"
    context = service._children[child["agent_id"]].context
    with pytest.raises(AgentToolError) as caught:
        await service.execute("subagent", {"prompt": "x"}, context)
    assert caught.value.code == "depth_limit"
    await service.execute("send_message", {"agent_id": child["agent_id"], "message": "queued"}, ROOT)
    with pytest.raises(AgentToolError) as caught:
        await service.execute("send_message", {"agent_id": child["agent_id"], "message": "extra"}, ROOT)
    assert caught.value.code == "queue_limit"
    small = factory(max_state_bytes=1024)
    with pytest.raises(AgentToolError) as caught:
        await small.execute("subagent", {"prompt": "x" * 2000}, ROOT)
    assert caught.value.code == "state_limit" and not small._children
    with pytest.raises(AgentToolError) as caught:
        await small.execute("subagent_fork", {"prompt": "x"}, ROOT, history=[{"content": float("nan")}])
    assert caught.value.code == "invalid_json"


async def test_fork_explicit_deep_snapshot_and_regular_child_fresh(factory):
    calls = []

    async def invoke(context, messages):
        calls.append(messages)
        return await echo(context, messages)

    service = factory(invoke)
    with pytest.raises(AgentToolError) as caught:
        await service.execute("subagent_fork", {"prompt": "fork"}, ROOT)
    assert caught.value.code == "history_required"
    history = [{"role": "user", "content": [{"type": "text", "text": "original"}]}]
    child = await service.execute("subagent_fork", {"prompt": "fork"}, ROOT, history=history)
    history[0]["content"][0]["text"] = "mutated"
    await settled(service, child["agent_id"])
    assert calls[0][0]["content"][0]["text"] == "original"
    await service.execute("subagent", {"prompt": "fresh", "run_in_background": False}, ROOT, history=history)
    assert calls[-1] == [{"role": "user", "content": "fresh"}]
    await service.execute("subagent_fork", {"prompt": "empty", "run_in_background": False}, ROOT, history=[])
    assert len(calls[-1]) == 1


async def test_parallel_cancellation_drains_every_invoke(factory):
    both_started, cleanup_started, finish_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    started, cleaned = set(), set()

    async def invoke(context, messages):
        started.add(context.agent_id)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await finish_cleanup.wait()
            cleaned.add(context.agent_id)

    service = factory(invoke)
    workflow = asyncio.create_task(service.execute("workflow", {"mode": "parallel", "steps": [{"prompt": "a"}, {"prompt": "b"}]}, ROOT))
    await asyncio.wait_for(both_started.wait(), 3)
    workflow.cancel()
    await asyncio.wait_for(cleanup_started.wait(), 3)
    assert not workflow.done()
    finish_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(workflow, 3)
    assert cleaned == started and len(cleaned) == 2
    assert all(child.runner.done() for child in service._children.values())


async def test_parallel_and_pipeline_bounded_declarative_execution(factory):
    calls = []

    async def invoke(context, messages):
        calls.append((context, messages))
        return await echo(context, messages)

    service = factory(invoke, max_workflow_steps=2)
    parallel = await service.execute("workflow", {"mode": "parallel", "steps": [{"prompt": "a"}, {"prompt": "b"}]}, ROOT)
    assert parallel["status"] == "completed" and len(parallel["results"]) == 2
    assert all(len(messages) == 1 and not context.human_request for context, messages in calls)
    pipeline = await service.execute("workflow", {"mode": "pipeline", "steps": [{"prompt": "first"}, {"prompt": "second"}]}, ROOT)
    assert pipeline["status"] == "completed"
    assert "reply:first" in calls[-1][1][0]["content"]
    assert "untrusted" in calls[-1][1][0]["content"]
    for args in [{"mode": "parallel", "steps": [{"prompt": "x", "code": "exec()"}]},
                 {"mode": "parallel", "steps": [{"prompt": "x"}] * 3},
                 {"mode": "javascript", "steps": [{"prompt": "x"}]},
                 {"mode": [], "steps": [{"prompt": "x"}]}]:
        with pytest.raises(AgentToolError):
            await service.execute("workflow", args, ROOT)


@pytest.mark.parametrize("report,expected,rounds", [
    ({"status": "continue", "summary": "more"}, "round_limit", 3),
    ({"status": "complete", "summary": "done", "evidence": ["test passed"]}, "worker_complete", 1),
    ({"status": "complete", "summary": "unsupported"}, "round_limit", 3),
    ({"status": "blocked", "blocked_reason": "missing fixture"}, "worker_blocked", 1),
    ({"status": "blocked"}, "round_limit", 3),
    ({"status": []}, "round_limit", 3),
    ("invalid JSON", "round_limit", 3),
])
async def test_ralph_fresh_rounds_structured_reports_and_cap(factory, report, expected, rounds):
    calls = []

    async def invoke(context, messages):
        calls.append((context, messages))
        content = json.dumps(report) if isinstance(report, dict) else report
        return [*messages, {"role": "assistant", "content": content}]

    service = factory(invoke, max_rounds=3, max_children=1)
    result = await service.execute("ralph", {"objective": "finish safely"}, ROOT,
                                   history=[{"role": "user", "content": "NEVER INHERIT THIS"}])
    assert result["status"] == expected and result["rounds"] == rounds
    assert result["independently_verified"] is False
    assert len({context.agent_id for context, _ in calls}) == rounds
    assert all(len(messages) == 1 and "NEVER INHERIT THIS" not in str(messages)
               and not context.human_request for context, messages in calls)
    if rounds > 1:
        assert "Previous structured worker report" in calls[1][1][0]["content"]
    with pytest.raises(AgentToolError) as caught:
        await service.execute("ralph", {"objective": "x", "max_rounds": 4}, ROOT)
    assert caught.value.code == "round_limit"


async def test_invoke_failure_and_invalid_results_are_observable(factory):
    async def broken(context, messages):
        raise RuntimeError("secret token must not leak")

    service = factory(broken)
    result = await service.execute("subagent", {"prompt": "x", "run_in_background": False}, ROOT)
    assert result["status"] == "idle" and result["outcome"] == "failed"
    assert result["error"] == "invoke_failed" and "secret" not in str(result)

    async def invalid(context, messages):
        return messages

    service = factory(invalid)
    result = await service.execute("subagent", {"prompt": "x", "run_in_background": False}, ROOT)
    assert result["error"] == "invalid_result"


async def test_cancel_suppressed_by_invoke_does_not_commit_completion(factory):
    started, canceled, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def invoke(context, messages):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            await finish.wait()
            return [*messages, {"role": "assistant", "content": "must not commit"}]

    service = factory(invoke)
    result = await service.execute("subagent", {"prompt": "x"}, ROOT)
    await asyncio.wait_for(started.wait(), 3)
    stop = asyncio.create_task(service.execute("interrupt_agent", {"agent_id": result["agent_id"]}, ROOT))
    await asyncio.wait_for(canceled.wait(), 3)
    assert not stop.done()
    finish.set()
    result = await asyncio.wait_for(stop, 3)
    assert result["outcome"] == "interrupted" and result["turns"] == 0
    assert result["summary"] == ""


async def test_oversized_completion_rolls_back_and_session_stays_valid(factory):
    async def invoke(context, messages):
        return [*messages, {"role": "assistant", "content": "x" * 1400}]

    service = factory(invoke, max_state_bytes=2200)
    result = await service.execute("subagent", {"prompt": "small", "run_in_background": False}, ROOT)
    assert result["outcome"] == "failed" and result["error"] == "state_limit"
    assert result["turns"] == 0 and result["summary"] == ""
    record = json.loads(next(service.state_dir.glob("*.json")).read_text())
    assert record["messages"] == [{"role": "user", "content": "small"}]
    assert record["outcome"] == "failed"


async def test_parallel_capacity_failure_drains_children_created_so_far(factory):
    calls = []

    async def invoke(context, messages):
        calls.append(context.agent_id)
        await asyncio.Event().wait()

    service = factory(invoke, max_children=1)
    with pytest.raises(AgentToolError) as caught:
        await service.execute("workflow", {"mode": "parallel", "steps": [{"prompt": "a"}, {"prompt": "b"}]}, ROOT)
    assert caught.value.code == "child_limit"
    assert not calls
    assert all(child.runner.done() and child.status == "idle" for child in service._children.values())


async def test_ralph_retained_session_cap_is_enforced(factory):
    async def invoke(context, messages):
        return [*messages, {"role": "assistant", "content": '{"status":"continue"}'}]

    service = factory(invoke, max_sessions=2, max_rounds=3)
    with pytest.raises(AgentToolError) as caught:
        await service.execute("ralph", {"objective": "bounded work"}, ROOT)
    assert caught.value.code == "session_limit"
    assert len(service._children) == 2 and all(child.runner.done() for child in service._children.values())
