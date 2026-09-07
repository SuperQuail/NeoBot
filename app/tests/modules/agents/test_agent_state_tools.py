"""State-only tests: no real chat history, credentials, model or bootstrap imports."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.state import StateTools


ROOT = ToolContext(owner="owner-a", chat_flow_id="group:42", user_id=7, human_request=True)
AUTO = replace(ROOT, human_request=False)
CHILD = replace(ROOT, agent_id="worker", parent_agent_id="main", depth=1)
QUESTIONS = {"questions": [{"id": "choice", "question": "Which option?", "options": [{"label": "A"}]}]}


@pytest.fixture
def state(tmp_path):
    instance = StateTools(tmp_path)
    yield instance
    instance.close()


@contextmanager
def error(code):
    with pytest.raises(AgentToolError, match=".") as caught:
        yield caught
    assert caught.value.code == code


async def create(state, maximum=4):
    return (await state.execute("create_goal", {"objective": "Finish verified work", "max_goal_rounds": maximum}, ROOT))["goal"]


async def update(state, action, context=ROOT, **kwargs):
    goal = (await state.execute("get_goal", {}, context))["goal"]
    return await state.execute("update_goal", {"goal_id": goal["goal_id"], "revision": goal["revision"], "action": action, **kwargs}, context)


async def test_todo_full_replacement_and_validation(state):
    result = await state.execute("todo_write", {"todos": [{"content": "one", "status": "pending"}, {"content": "two", "status": "in_progress"}]}, ROOT)
    assert result["counts"] == {"pending": 1, "in_progress": 1, "completed": 0}
    result = await state.execute("todo_write", {"todos": [{"content": "two", "status": "completed"}]}, ROOT)
    assert result["todos"] == [{"content": "two", "status": "completed"}]
    for item in ({"content": "bad", "status": "done"}, {"content": "bad", "status": []}, {"content": "", "status": "pending"}):
        with error("invalid_arguments") as caught:
            await state.execute("todo_write", {"todos": [item]}, ROOT)
        assert caught.value.code == "invalid_arguments"
    assert (await state.execute("todo_write", {"todos": []}, ROOT))["todos"] == []


@pytest.mark.parametrize("other", [replace(ROOT, owner="other"), replace(ROOT, chat_flow_id="group:43"), CHILD])
async def test_owner_chat_agent_state_isolation(state, other):
    goal = await create(state)
    question = await state.execute("ask_user_question", QUESTIONS, ROOT)
    assert (await state.execute("get_goal", {}, other))["goal"] is None
    with error("not_found") as caught:
        await state.execute("question_status", {"question_id": question["question_id"]}, other)
    assert caught.value.code == "not_found"
    with error("not_found"):
        state.record_answer(other, question["question_id"], "A", "m1")
    if other.depth == 0:
        with error("not_found"):
            await state.execute("update_goal", {"goal_id": goal["goal_id"], "revision": 1, "action": "pause"}, other)


async def test_question_only_genuine_host_answer_and_replay_guard(state):
    q = await state.execute("ask_user_question", QUESTIONS, AUTO)
    assert q["status"] == "pending" and "answer" not in q
    with error("unknown_tool") as caught:
        await state.execute("record_answer", {"question_id": q["question_id"], "answer": "A"}, ROOT)
    assert caught.value.code == "unknown_tool"
    with error("invalid_arguments"):
        await state.execute("ask_user_question", {**QUESTIONS, "answer": "A"}, ROOT)
    with error("permission_denied"):
        state.record_answer(AUTO, q["question_id"], "A", "m1")
    with error("permission_denied"):
        state.record_answer(replace(ROOT, user_id=8), q["question_id"], "A", "m1")
    answer = state.record_answer(ROOT, q["question_id"], "A", "m1")
    assert answer["status"] == "answered" and answer["answer"] == {"choice": "A"}
    stored = await state.execute("question_status", {"question_id": q["question_id"]}, AUTO)
    assert stored["message_id"] == "m1"
    q2 = await state.execute("ask_user_question", QUESTIONS, AUTO)
    with error("conflict") as caught:
        state.record_answer(ROOT, q2["question_id"], "A", "m1")
    assert caught.value.code == "conflict"
    assert (await state.execute("question_status", {"question_id": q2["question_id"]}, ROOT))["status"] == "pending"


async def test_host_cross_owner_question_routing_is_user_and_chat_bound(state):
    solver = replace(CHILD, owner="solver-session")
    q = await state.execute("ask_user_question", QUESTIONS, solver)
    with error("not_found"):
        await state.execute("question_status", {"question_id": q["question_id"]}, ROOT)
    for chat, user in (("group:43", 7), ("group:42", 8), ("group:42", None)):
        with error("not_found"):
            state.resolve_pending_question(chat, user, q["question_id"])
    origin = state.resolve_pending_question("group:42", 7, q["question_id"])
    assert origin == solver
    state.record_answer(origin, q["question_id"], "A", "genuine-message")
    with error("not_found"):
        state.resolve_pending_question("group:42", 7, q["question_id"])


async def test_question_limits_and_validation(state):
    for args in ({"questions": []}, {"questions": QUESTIONS["questions"] * 2}, {"questions": [{"id": "x", "question": "q", "answer": "forged"}]}):
        with error("invalid_arguments"):
            await state.execute("ask_user_question", args, ROOT)
    for _ in range(20):
        await state.execute("ask_user_question", QUESTIONS, ROOT)
    with error("limit_exceeded") as caught:
        await state.execute("ask_user_question", QUESTIONS, ROOT)
    assert caught.value.code == "limit_exceeded"


@pytest.mark.parametrize("context", [AUTO, CHILD, replace(ROOT, parent_agent_id="parent"), replace(ROOT, depth=1)])
async def test_goal_creation_requires_root_human(state, context):
    with error("permission_denied") as caught:
        await state.execute("create_goal", {"objective": "No forged intent"}, context)
    assert caught.value.code == "permission_denied"


async def test_goal_update_permissions_and_model_authority_args(state):
    await create(state)
    for action in ("edit", "pause", "resume"):
        with error("permission_denied") as caught:
            await update(state, action, AUTO)
        assert caught.value.code == "permission_denied"
    for name, args in (("create_goal", {"objective": "x", "human_request": True}), ("get_goal", {"owner": "other"}), ("get_goal", {"chat_flow_id": "other:1"})):
        with error("invalid_arguments"):
            await state.execute(name, args, AUTO)
    with error("insufficient_rounds") as caught:
        await update(state, "blocked", AUTO, blocked_reason="network unavailable")
    assert caught.value.code == "insufficient_rounds"


async def test_goal_cas_across_sqlite_connections(state, tmp_path):
    goal = await create(state)
    second = StateTools(tmp_path, recover=False)
    try:
        await update(second, "pause")
        with error("version_conflict") as caught:
            await state.execute("update_goal", {"goal_id": goal["goal_id"], "revision": goal["revision"], "action": "complete"}, ROOT)
        assert caught.value.code == "version_conflict"
        assert (await state.execute("get_goal", {}, ROOT))["goal"]["phase"] == "paused"
    finally:
        second.close()


async def test_goal_round_reservation_budget_and_resume(state):
    await create(state, 2)
    for index in range(2):
        reserved = state.next_goal_round(AUTO)
        assert reserved["round"]["number"] == index + 1
        assert state.next_goal_round(AUTO)["round"] is None
        result = state.record_goal_round(AUTO, reserved["round"]["round_id"], "continue")
        with error("conflict"):
            state.record_goal_round(AUTO, reserved["round"]["round_id"], "continue")
    assert result["activation"] == "disarmed" and result["goal"]["phase"] == "active"
    assert state.next_goal_round(ROOT)["round"] is None
    with error("budget_exhausted") as caught:
        await update(state, "resume")
    assert caught.value.code == "budget_exhausted"
    await update(state, "edit", max_goal_rounds=3)
    assert state.next_goal_round(ROOT)["round"] is None  # budget edit alone never rearms
    await update(state, "resume")
    assert state.next_goal_round(AUTO)["round"]["number"] == 3


async def test_goal_blocked_requires_same_three_consecutive_host_reports(state):
    await create(state, 8)
    for reason, expected in (("a", 1), ("b", 1), ("b", 2), ("b", 3)):
        reserved = state.next_goal_round(AUTO)
        result = state.record_goal_round(AUTO, reserved["round"]["round_id"], "blocked", reason)
        assert result["goal"]["blocker_streak"] == expected
        assert result["goal"]["phase"] == ("blocked" if expected == 3 else "active")
    assert state.next_goal_round(AUTO)["round"] is None
    resumed = await update(state, "resume")
    assert resumed["goal"]["blocker_streak"] == 0
    with error("insufficient_rounds"):
        await update(state, "blocked", blocked_reason="b")


async def test_human_pause_survives_late_round_result(state):
    await create(state)
    round_id = state.next_goal_round(AUTO)["round"]["round_id"]
    with error("conflict"):
        await update(state, "edit", objective="different")
    await update(state, "pause")
    result = state.record_goal_round(AUTO, round_id, "complete")
    assert result["goal"]["phase"] == "paused" and result["activation"] == "disarmed"


async def test_restart_disarms_goals_and_marks_pending_without_forging_answers(tmp_path):
    first = StateTools(tmp_path)
    await create(first)
    q = await first.execute("ask_user_question", QUESTIONS, ROOT)
    await first.execute("enter_plan_mode", {}, ROOT)
    plan = await first.execute("exit_plan_mode", {"plan": "# Plan"}, ROOT)
    round_id = first.next_goal_round(AUTO)["round"]["round_id"]
    first.close()
    second = StateTools(tmp_path)
    try:
        result = await second.execute("get_goal", {}, ROOT)
        assert result["activation"] == "disarmed"
        assert result["goal"]["rounds"][-1]["status"] == "interrupted"
        assert second.next_goal_round(ROOT)["round"] is None
        with error("conflict"):
            second.record_goal_round(AUTO, round_id, "continue")
        status = await second.execute("question_status", {"question_id": q["question_id"]}, ROOT)
        assert status["status"] == "interrupted" and "answer" not in status
        second.record_answer(ROOT, q["question_id"], "A", "after-restart")
        assert second.pending_requests(ROOT)["plan"]["status"] == "interrupted"
        assert second.is_planning(ROOT)
        with error("conflict"):
            second.record_plan_decision(ROOT, plan["plan_id"], True, "stale-plan")
        with error("permission_denied"):
            await update(second, "resume", AUTO)
        await update(second, "resume")
        assert second.next_goal_round(AUTO)["round"]["number"] == 2
    finally:
        second.close()


async def test_plan_approval_is_host_only_and_execution_gate_stays_closed(state):
    assert not state.is_planning(ROOT)
    await state.execute("enter_plan_mode", {}, ROOT)
    assert state.is_planning(ROOT)
    with error("invalid_arguments"):
        await state.execute("exit_plan_mode", {"plan": "# Plan", "approved": True}, ROOT)
    plan = await state.execute("exit_plan_mode", {"plan": "# Plan"}, ROOT)
    assert plan["status"] == "pending" and state.is_planning(ROOT)
    with error("permission_denied"):
        state.record_plan_decision(AUTO, plan["plan_id"], True, "m1")
    with error("permission_denied"):
        state.record_plan_decision(replace(ROOT, user_id=8), plan["plan_id"], True, "m1")
    assert state.record_plan_decision(ROOT, plan["plan_id"], True, "m1")["approved"]
    assert not state.is_planning(ROOT)


async def test_plan_async_callback_credentials_retry_keeps_pending(tmp_path):
    calls = []

    async def approve(context, plan):
        calls.append((context, plan))
        if len(calls) == 1:
            raise AgentToolError("CREDENTIAL_REQUIRED", "Host approval missing")
        return True

    state = StateTools(tmp_path, approve=approve)
    try:
        await state.execute("enter_plan_mode", {}, ROOT)
        with error("CREDENTIAL_REQUIRED") as caught:
            await state.execute("exit_plan_mode", {"plan": "# Plan"}, AUTO)
        assert caught.value.code == "CREDENTIAL_REQUIRED"
        assert state.pending_requests(ROOT)["plan"]["status"] == "pending"
        with error("conflict"):
            await state.execute("exit_plan_mode", {"plan": "# Changed"}, ROOT)
        result = await state.execute("exit_plan_mode", {"plan": "# Plan"}, AUTO)
        assert result["approved"] and not state.is_planning(ROOT)
        assert calls[0][1]["plan_id"] == calls[1][1]["plan_id"]
    finally:
        state.close()


async def test_plan_callback_cancellation_and_host_cancel(state):
    async def cancelled(context, plan):
        raise asyncio.CancelledError

    state.approve = cancelled
    await state.execute("enter_plan_mode", {}, ROOT)
    with pytest.raises(asyncio.CancelledError):
        await state.execute("exit_plan_mode", {"plan": "# Plan"}, ROOT)
    assert state.pending_requests(ROOT)["plan"]["status"] == "interrupted"
    await create(state)
    q = await state.execute("ask_user_question", QUESTIONS, ROOT)
    state.next_goal_round(AUTO)
    state.cancel_pending(ROOT)
    assert state.next_goal_round(ROOT)["round"] is None
    with error("conflict"):
        state.record_answer(ROOT, q["question_id"], "A", "cancelled")


async def test_audit_isolated_redacted_bounded_and_not_real_history(tmp_path):
    (tmp_path / "real_chat_history.json").write_text('{"private":"DO_NOT_READ_CHAT"}')
    state = StateTools(tmp_path / "state", max_events_per_scope=3)
    try:
        assert (await state.execute("session_search", {}, ROOT))["events"] == []
        await state.execute("todo_write", {"todos": []}, ROOT)
        assert (await state.execute("session_search", {}, ROOT))["events"] == []  # parent audits explicitly
        event = state.record_event(ROOT, "run_code", {"code": "print('FULL_PYTHON_SOURCE')", "api_key": "SECRET_KEY", "SECRET_KEY_AS_KEY": "anything"}, {"status": "completed", "body": "PRIVATE_BODY"})
        other = replace(ROOT, owner="other")
        for context in (other, replace(ROOT, chat_flow_id="group:43")):
            assert (await state.execute("session_trace", {}, context))["events"] == []
            with error("not_found"):
                await state.execute("session_event_read", {"event_id": event["event_id"]}, context)
        content = await state.execute("session_event_read", {"event_id": event["event_id"]}, ROOT)
        raw = json.dumps(content)
        for secret in ("FULL_PYTHON_SOURCE", "SECRET_KEY", "SECRET_KEY_AS_KEY", "PRIVATE_BODY", "DO_NOT_READ_CHAT"):
            assert secret not in raw
        assert "completed" in raw and content["source"] == "new_tool_audit"
        assert (await state.execute("session_event_search", {"query": "run_code"}, CHILD))["events"]
        for _ in range(4):
            state.record_event(ROOT, "todo_write", {"todos": []}, {"status": "completed"})
        assert len((await state.execute("session_event_trace", {"limit": 100}, ROOT))["events"]) == 3
        first = await state.execute("session_search", {"limit": 2}, ROOT)
        second = await state.execute("session_search", {"limit": 2, "before": first["next_before"]}, ROOT)
        assert len(first["events"]) == 2 and len(second["events"]) == 1
        for args in ({"limit": 101}, {"limit": 0}, {"limit": True}, {"query": "x" * 201}, {"before": -1}, {"owner": "other"}):
            with error("invalid_arguments"):
                await state.execute("session_search", args, ROOT)
        assert not (await state.execute("session_event_search", {"query": "%' OR 1=1 --"}, ROOT))["events"]
    finally:
        state.close()


async def test_concurrent_host_reservations_consume_one_round(state, tmp_path):
    await create(state)
    second = StateTools(tmp_path, recover=False)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(instance.next_goal_round, AUTO) for instance in (state, second)]
            reservations = [future.result()["round"] for future in futures]
        assert sum(item is not None for item in reservations) == 1
        assert (await state.execute("get_goal", {}, ROOT))["goal"]["rounds_started"] == 1
    finally:
        second.close()


@pytest.mark.parametrize("outcome", ["error", "cancelled"])
async def test_failed_host_round_never_autocontinues(state, outcome):
    await create(state)
    with error("permission_denied"):
        state.next_goal_round(CHILD)
    round_id = state.next_goal_round(AUTO)["round"]["round_id"]
    result = state.record_goal_round(AUTO, round_id, outcome)
    assert result["activation"] == "disarmed" and result["goal"]["phase"] == "active"
    assert state.next_goal_round(AUTO)["round"] is None
    await update(state, "resume")
    round_id = state.next_goal_round(AUTO)["round"]["round_id"]
    result = state.record_goal_round(AUTO, round_id, "complete")
    assert result["goal"]["phase"] == "complete"
    with error("invalid_state"):
        await update(state, "resume")
    assert (await create(state))["revision"] == 1


async def test_audit_large_and_cyclic_structures_are_metadata_only(state):
    nested = {"code": "SECRET_SOURCE" * 100_000}
    for _ in range(4):
        nested = {key: nested for key in ("goal", "todos", "questions", "events", "result", "results", "counts", "round")}
    event = state.record_event(ROOT, "run_code", nested, nested)
    content = await state.execute("session_event_read", {"event_id": event["event_id"]}, ROOT)
    assert len(json.dumps(content).encode()) < 16_384
    assert "SECRET_SOURCE" not in json.dumps(content)
    cycle = {"status": "pending"}
    cycle["goal"] = cycle
    state.record_event(ROOT, "host_event", cycle, cycle)


async def test_strict_json_limits_and_goal_bounds(state):
    for maximum in (0, -1, 26, True):
        with error("invalid_arguments"):
            await state.execute("create_goal", {"objective": "work", "max_goal_rounds": maximum}, ROOT)
    with error("limit_exceeded") as caught:
        await state.execute("exit_plan_mode", {"plan": "x" * 70_000}, ROOT)
    assert caught.value.code == "limit_exceeded"
    await create(state)
    with error("invalid_arguments"):
        await update(state, [], ROOT)
    host_names = {"record_answer", "record_event", "next_goal_round", "record_goal_round", "cancel_pending", "resolve_pending_question", "record_plan_decision", "is_planning"}
    assert not host_names.intersection(d["function"]["name"] for d in state.definitions())
