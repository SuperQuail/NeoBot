"""Host goal driver tests, with deterministic fake Agent callbacks and SQLite."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.goal_driver import GoalDriver
from neobot_app.agent_tools.state import StateTools


ROOT = ToolContext(owner="root", chat_flow_id="group:1", agent_id="root-agent", user_id=42, human_request=True)
AUTO = replace(ROOT, human_request=False)


@pytest.fixture
def state(tmp_path):
    store = StateTools(tmp_path)
    yield store
    store.close()


async def create(state, context=ROOT, maximum=3):
    return await state.execute("create_goal", {"objective": "Finish and verify the work", "max_goal_rounds": maximum}, context)


async def goal(state, context=ROOT):
    return await state.execute("get_goal", {}, context)


async def update(state, action, context=ROOT):
    current = (await goal(state, context))["goal"]
    return await state.execute("update_goal", {"goal_id": current["goal_id"], "revision": current["revision"], "action": action}, context)


async def test_real_continuation_runs_same_agent_without_human_authority_until_budget(state):
    calls, notices = [], []

    async def invoke(context, messages):
        assert context == AUTO and driver.is_running_round(context)
        calls.append(messages)
        assert "NOT A NEW HUMAN REQUEST" in messages[-1]["content"]
        return messages + [{"role": "assistant", "content": "More verified progress"}]

    async def notify(context, result):
        assert not driver.is_running_round(context)
        notices.append(result)

    driver = GoalDriver(state, invoke, notify)
    try:
        await create(state)
        assert driver.schedule(ROOT, [{"role": "user", "content": "Original objective"}]) is True
        assert driver.schedule(ROOT, []) is False
        await driver.wait(ROOT)
        result = await goal(state)
        assert len(calls) == len(notices) == 3
        assert result["goal"]["rounds_started"] == 3 and result["activation"] == "disarmed"
        assert all(r["status"] == "continue" for r in result["goal"]["rounds"])
        assert "not_independently_verified" in notices[-1]["completion_basis"]
        assert not driver.schedule(ROOT, [])
    finally:
        await driver.shutdown()


async def test_model_phase_not_text_claim_stops_driver(state):
    notices = []

    async def invoke(context, messages):
        await update(state, "complete", context)
        return messages + [{"role": "assistant", "content": "Finished"}]

    async def notify(context, result):
        notices.append(result)

    driver = GoalDriver(state, invoke, notify)
    await create(state)
    driver.schedule(ROOT, [])
    await driver.wait()
    assert (await goal(state))["goal"]["phase"] == "complete"
    assert len(notices) == 1 and notices[0]["outcome"] == "complete"
    assert notices[0]["goal"]["rounds"][-1]["status"] == "pending"  # notification is pre-settlement
    await driver.shutdown()


async def test_running_round_identity_rejects_other_tasks_scope_human_and_children(state):
    entered, release = asyncio.Event(), asyncio.Event()
    checks = []

    async def invoke(context, messages):
        checks.append(driver.is_running_round(context))
        assert not driver.is_running_round(ROOT)
        assert not driver.is_running_round(replace(context, agent_id="forged"))
        assert not driver.is_running_round(replace(context, chat_flow_id="group:other"))
        assert not driver.is_running_round(replace(context, depth=1))

        async def spoof():
            return driver.is_running_round(context)

        assert not await asyncio.create_task(spoof())
        entered.set()
        await release.wait()
        return messages

    async def notify(context, result):
        pass

    driver = GoalDriver(state, invoke, notify)
    await create(state, maximum=1)
    driver.schedule(ROOT, [])
    await entered.wait()
    assert not driver.is_running_round(AUTO)
    release.set()
    await driver.wait()
    assert checks == [True] and not driver.is_running_round(AUTO)
    await driver.shutdown()


@pytest.mark.parametrize("waiting", ["question", "plan"])
async def test_existing_pending_requests_disarm_without_invoke_or_cancelling_them(state, waiting):
    notices = []

    async def invoke(context, messages):
        pytest.fail("Cannot invoke while waiting for human input")

    async def notify(context, result):
        notices.append(result)

    await create(state)
    if waiting == "question":
        await state.execute("ask_user_question", {"questions": [{"id": "q", "question": "Choose?"}]}, ROOT)
    else:
        await state.execute("enter_plan_mode", {}, ROOT)
        await state.execute("exit_plan_mode", {"plan": "# Plan"}, ROOT)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await driver.wait()
    assert notices[0]["status"] == "waiting_for_human"
    assert (await goal(state))["activation"] == "disarmed"
    pending = state.pending_requests(ROOT)
    request = pending["questions"][0] if waiting == "question" else pending["plan"]
    assert request["status"] == "pending"
    assert not driver.schedule(ROOT, [])
    await driver.shutdown()


async def test_questions_created_by_invoke_stop_at_end_and_remain_answerable(state):
    calls = 0

    async def invoke(context, messages):
        nonlocal calls
        calls += 1
        await state.execute("ask_user_question", {"questions": [{"id": "q", "question": "Choose?"}]}, context)
        return messages

    async def notify(context, result):
        assert result["reason"] == "pending_question"

    await create(state)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await driver.wait()
    assert calls == 1 and (await goal(state))["activation"] == "disarmed"
    pending = state.pending_requests(ROOT)["questions"][0]
    state.record_answer(ROOT, pending["question_id"], "real answer", "human-message")
    assert not driver.schedule(ROOT, [])  # answer alone does not resume a goal
    await driver.shutdown()


@pytest.mark.parametrize("failure", ["exception", "tool_result", "provider_result", "notify", "invalid_return"])
async def test_failures_never_busy_retry_or_leave_armed(state, failure):
    calls = 0

    async def invoke(context, messages):
        nonlocal calls
        calls += 1
        if failure == "exception":
            raise AgentToolError("CREDENTIAL_REQUIRED", "secret details not logged")
        if failure == "tool_result":
            return messages + [{"role": "tool", "tool_call_id": "denied", "content": '{"code":"CREDENTIAL_REQUIRED"}'}]
        if failure == "provider_result":
            return messages + [{"role": "assistant", "content": "Error: Provider failed"}]
        if failure == "invalid_return":
            return {"not": "messages"}
        return messages

    async def notify(context, result):
        if failure == "notify":
            raise RuntimeError("delivery failed")

    await create(state)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await driver.wait()
    current = await goal(state)
    assert calls == 1 and current["activation"] == "disarmed"
    assert current["goal"]["pending_round_id"] is None
    assert current["goal"]["rounds"][-1]["status"] == "error"
    assert not driver.schedule(ROOT, [])
    await driver.shutdown()


async def test_cancel_before_task_starts_records_cancelled_reservation(state):
    async def invoke(context, messages):
        pytest.fail("Task should not have started")

    async def notify(context, result):
        pass

    await create(state)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await driver.cancel(ROOT)
    result = await goal(state)
    assert result["activation"] == "disarmed"
    assert result["goal"]["rounds"][-1]["status"] == "cancelled"
    assert result["goal"]["pending_round_id"] is None
    await driver.shutdown()


async def test_human_interrupt_cancels_all_same_chat_owners_but_not_other_chat(state):
    contexts = [ROOT, replace(ROOT, owner="same-chat-other-owner"), replace(ROOT, owner="other-chat", chat_flow_id="group:2")]
    entered = {c.owner: asyncio.Event() for c in contexts}
    finalized = set()
    release = asyncio.Event()

    async def invoke(context, messages):
        entered[context.owner].set()
        try:
            await release.wait()
        finally:
            finalized.add(context.owner)
        return messages

    async def notify(context, result):
        pass

    driver = GoalDriver(state, invoke, notify)
    for context in contexts:
        await create(state, context, maximum=1)
        driver.schedule(context, [])
    await asyncio.gather(*(event.wait() for event in entered.values()))
    with pytest.raises(AgentToolError):
        await driver.cancel_for_human(AUTO)
    await driver.cancel_for_human(ROOT)
    assert finalized == {ROOT.owner, "same-chat-other-owner"}
    assert (await goal(state))["goal"]["rounds"][-1]["status"] == "cancelled"
    assert (await goal(state, contexts[2]))["goal"]["pending_round_id"] is not None
    release.set()
    await driver.wait()
    await driver.shutdown()


async def test_shutdown_drains_active_round_and_prevents_reschedule(state):
    entered, finalized = asyncio.Event(), asyncio.Event()

    async def invoke(context, messages):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finalized.set()
        return messages

    async def notify(context, result):
        pass

    await create(state)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await entered.wait()
    await driver.shutdown()
    assert finalized.is_set()
    assert (await goal(state))["goal"]["rounds"][-1]["status"] == "cancelled"
    await update(state, "resume")
    assert not driver.schedule(ROOT, [])
    await driver.shutdown()


async def test_restart_and_reconstruction_never_automatically_schedule(tmp_path):
    first = StateTools(tmp_path)
    await create(first)
    first.close()
    second = StateTools(tmp_path)
    calls = []

    async def invoke(context, messages):
        calls.append(context)
        await update(second, "complete", context)
        return messages

    async def notify(context, result):
        pass

    driver = GoalDriver(second, invoke, notify)
    try:
        assert not calls and not driver.schedule(ROOT, [])
        await update(second, "resume")
        assert driver.schedule(ROOT, [])
        await driver.wait()
        assert len(calls) == 1
    finally:
        await driver.shutdown()
        second.close()


async def test_notify_can_cancel_its_own_driver_without_deadlock(state):
    calls = 0

    async def invoke(context, messages):
        nonlocal calls
        calls += 1
        return messages

    async def notify(context, result):
        await driver.cancel(context)

    await create(state)
    driver = GoalDriver(state, invoke, notify)
    driver.schedule(ROOT, [])
    await driver.wait()
    assert calls == 1
    assert (await goal(state))["goal"]["rounds"][-1]["status"] == "cancelled"
    await driver.shutdown()


async def test_maximum_control_character_objective_fits_minimum_budget(state):
    calls = 0

    async def invoke(context, messages):
        nonlocal calls
        calls += 1
        assert len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()) <= 1024
        return messages

    async def notify(context, result):
        pass

    await state.execute("create_goal", {"objective": "goal" + chr(0) * 7996, "max_goal_rounds": 1}, ROOT)
    driver = GoalDriver(state, invoke, notify, max_history_bytes=1024)
    driver.schedule(ROOT, [{"role": "user", "content": "history" * 1000}])
    await driver.wait()
    assert calls == 1
    await driver.shutdown()


async def test_root_schedule_gate_and_one_task_per_owner(state):
    entered, release = asyncio.Event(), asyncio.Event()

    async def invoke(context, messages):
        entered.set()
        await release.wait()
        return messages

    async def notify(context, result):
        pass

    await create(state, maximum=1)
    other_chat = replace(ROOT, chat_flow_id="group:2")
    await create(state, other_chat, maximum=1)
    driver = GoalDriver(state, invoke, notify)
    for context in (replace(ROOT, depth=1), replace(ROOT, parent_agent_id="parent")):
        with pytest.raises(AgentToolError):
            driver.schedule(context, [])
    assert driver.schedule(ROOT, [])
    await entered.wait()
    assert not driver.schedule(other_chat, [])
    assert (await goal(state, other_chat))["goal"]["rounds_started"] == 0
    await driver.cancel(other_chat)  # wrong chat cannot cancel current owner task
    assert (await goal(state))["goal"]["pending_round_id"] is not None
    release.set()
    await driver.wait()
    await driver.shutdown()


async def test_history_and_protocol_groups_are_bounded_detached_and_well_formed(state):
    received = []
    history = [{"role": "user", "content": "雪" * 100_000},
               {"role": "tool", "tool_call_id": "orphan", "content": "ignore orphan"},
               {"role": "assistant", "tool_calls": [{"id": "good", "type": "function", "function": {"name": "get_goal", "arguments": "{}"}}]},
               {"role": "tool", "tool_call_id": "good", "content": "{}"},
               {"role": "assistant", "tool_calls": [{"id": "incomplete", "function": {"name": "get_goal", "arguments": "{}"}}]},
               {"role": "user", "content": "Recent request"}]

    async def invoke(context, messages):
        received.append(messages)
        assert len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()) <= 2048
        ids = {call["id"] for m in messages for call in m.get("tool_calls", [])}
        result_ids = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
        assert ids == result_ids
        assert "orphan" not in result_ids and "incomplete" not in ids
        return messages + [{"role": "assistant", "content": "Progress " * 1000}]

    async def notify(context, result):
        assert len(json.dumps(result["messages"], ensure_ascii=False, separators=(",", ":")).encode()) <= 2048

    await create(state, maximum=2)
    driver = GoalDriver(state, invoke, notify, max_history_bytes=2048)
    driver.schedule(ROOT, history)
    history[-1]["content"] = "MUTATED AFTER SCHEDULE"
    await driver.wait()
    assert len(received) == 2
    assert "MUTATED AFTER SCHEDULE" not in json.dumps(received)
    await driver.shutdown()
