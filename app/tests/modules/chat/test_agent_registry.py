"""AgentRegistry 生命周期加固测试：关闭幂等、在途调用排空、关闭后拒绝。"""

from __future__ import annotations

import asyncio
import gc
from types import SimpleNamespace
import weakref

import pytest

from neobot_chat.runtime.agent import Agent
from neobot_chat.tools.registry import AgentRegistry


class _HangingAgent:
    def __init__(self) -> None:
        self.closed = False
        self.invoke_started = asyncio.Event()
        self._release = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        await self._release.wait()
        return {"messages": [{"role": "assistant", "content": "done"}]}

    async def close(self) -> None:
        self.closed = True


class _QuickAgent:
    def __init__(self) -> None:
        self.closed = False

    async def invoke(self, state: dict) -> dict:
        return {"messages": [{"role": "assistant", "content": "quick"}]}

    async def close(self) -> None:
        self.closed = True


class _CountingAgent(_QuickAgent):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        await asyncio.sleep(0)
        self.closed = True


class _FailingCloseAgent(_QuickAgent):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        if self.close_count == 1:
            raise RuntimeError("close failed")
        self.closed = True


class _RetiredFailOnceAgent:
    """顽固 invoke + 首次 close 失败：验证 close() 对退役延迟关闭失败的重试。"""

    def __init__(self) -> None:
        self.closed = False
        self.close_count = 0
        self.invoke_started = asyncio.Event()
        self.release = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                continue
        return {"messages": [{"role": "assistant", "content": "released"}]}

    async def close(self) -> None:
        self.close_count += 1
        if self.close_count == 1:
            raise RuntimeError("close failed")
        self.closed = True


class _GatedCloseAgent:
    def __init__(self) -> None:
        self.closed = False
        self.invoke_started = asyncio.Event()
        self.release_invoke = asyncio.Event()
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        while not self.release_invoke.is_set():
            try:
                await self.release_invoke.wait()
            except asyncio.CancelledError:
                continue
        return {"messages": [{"role": "assistant", "content": "released"}]}

    async def close(self) -> None:
        self.close_started.set()
        await self.release_close.wait()
        self.closed = True


class _SlowCancelAgent:
    """invoke 收到取消后延迟完成，用于验证超时/取消路径确实等待了在途任务结束。"""

    def __init__(self) -> None:
        self.closed = False
        self.invoke_started = asyncio.Event()
        self.cancel_processed = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            self.cancel_processed.set()
            raise
        return {"messages": [{"role": "assistant", "content": "done"}]}

    async def close(self) -> None:
        self.closed = True


class _GatedAgent:
    """invoke 进入后阻塞，用于验证并发委托的加锁/并行行为。"""

    def __init__(self) -> None:
        self.closed = False
        self.invoke_count = 0
        self.invoke_started = asyncio.Event()
        self._release = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_count += 1
        self.invoke_started.set()
        await self._release.wait()
        return {
            "messages": [{"role": "assistant", "content": f"reply-{self.invoke_count}"}]
        }

    async def close(self) -> None:
        self.closed = True


class _PermanentCloseAgent(_QuickAgent):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        raise RuntimeError("permanent close failure")


class _TimeoutCloseAgent(_QuickAgent):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()
        self.cancel_count = 0

    async def close(self) -> None:
        self.close_count += 1
        self.close_started.set()
        try:
            await self.release_close.wait()
        except asyncio.CancelledError:
            self.cancel_count += 1
            raise
        self.closed = True


class _SlowDrainCleanupAgent:
    def __init__(self) -> None:
        self.closed = False
        self.invoke_started = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.release_cleanup = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cleanup_started.set()
            while not self.release_cleanup.is_set():
                try:
                    await self.release_cleanup.wait()
                except asyncio.CancelledError:
                    continue
            raise

    async def close(self) -> None:
        self.closed = True


async def test_close_is_idempotent_and_clears_state() -> None:
    registry = AgentRegistry()
    agent = _QuickAgent()
    registry.register("demo.echo", agent)

    await registry.close()
    await registry.close()

    assert agent.closed
    assert registry.names == []
    assert registry._agents == {}
    assert registry._sessions == {}
    assert registry._agent_close_tasks == {}


async def test_completed_agent_closes_are_not_retained() -> None:
    registry = AgentRegistry()

    for i in range(100):
        registry.register(f"demo.agent-{i}", _QuickAgent())
        await registry.unregister_and_drain(f"demo.agent-{i}")

    assert registry._agent_close_tasks == {}


async def test_runtime_agent_close_is_concurrently_idempotent() -> None:
    class Resource:
        def __init__(self) -> None:
            self.close_count = 0

        async def close(self) -> None:
            self.close_count += 1
            await asyncio.sleep(0)

    executor = Resource()
    provider = Resource()
    agent = object.__new__(Agent)
    agent.toolset = SimpleNamespace(executor=executor)
    agent.provider = provider
    agent._close_task = None

    await asyncio.gather(agent.close(), agent.close(), agent.close())
    await agent.close()

    assert executor.close_count == 1
    assert provider.close_count == 1


async def test_runtime_agent_close_failure_can_be_retried() -> None:
    class Resource:
        def __init__(self, fail_once: bool = False) -> None:
            self.close_count = 0
            self.fail_once = fail_once

        async def close(self) -> None:
            self.close_count += 1
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("resource close failed")

    executor = Resource(fail_once=True)
    provider = Resource()
    agent = object.__new__(Agent)
    agent.toolset = SimpleNamespace(executor=executor)
    agent.provider = provider
    agent._close_task = None

    with pytest.raises(RuntimeError, match="resource close failed"):
        await agent.close()
    await agent.close()

    assert executor.close_count == 2
    assert provider.close_count == 2


async def test_register_after_close_raises() -> None:
    registry = AgentRegistry()
    await registry.close()

    with pytest.raises(RuntimeError):
        registry.register("demo.echo", _QuickAgent())


async def test_delegate_after_close_returns_error() -> None:
    registry = AgentRegistry()
    registry.register("demo.echo", _QuickAgent())
    await registry.close()

    result = await registry.delegate(agent="demo.echo", task="hi")
    assert "closed" in result


async def test_close_drains_then_cancels_in_flight() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.2
    agent = _HangingAgent()
    registry.register("demo.slow", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.slow", task="go"))
    await agent.invoke_started.wait()

    await registry.close()

    assert agent.closed
    assert registry._in_flight == {}
    # 在途调用被取消后返回错误文本而非异常
    result = await delegate_task
    assert "AgentRegistry is closed" in result or "Agent 'demo.slow'" in result


async def test_close_with_same_session_waiter_keeps_bookkeeping_safe() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.02
    agent = _ForeverStubbornAgent()
    registry.register("demo.queued", agent)

    first = asyncio.create_task(
        registry.delegate(agent="demo.queued", task="first", session_id="same")
    )
    await agent.invoke_started.wait()
    second = asyncio.create_task(
        registry.delegate(agent="demo.queued", task="second", session_id="same")
    )
    while registry._session_lock_users.get("demo.queued:same") != 2:
        await asyncio.sleep(0)

    await asyncio.wait_for(registry.close(), timeout=1)
    assert first.done()
    assert second.done()

    agent.release.set()
    results = await asyncio.wait_for(
        asyncio.gather(first, second, return_exceptions=True), timeout=1
    )

    assert all(
        isinstance(result, asyncio.CancelledError) or "registry closed" in result
        for result in results
    )
    assert registry._session_lock_users == {}
    assert registry._session_locks == {}


async def test_unregister_clears_agent_sessions() -> None:
    registry = AgentRegistry()
    registry.register("demo.echo", _QuickAgent())

    await registry.delegate(agent="demo.echo", task="first", session_id="s1")
    assert "demo.echo:s1" in registry._sessions

    registry.unregister("demo.echo")

    assert "demo.echo:s1" not in registry._sessions
    assert registry.names == []


async def test_register_duplicate_name_raises() -> None:
    registry = AgentRegistry()
    registry.register("demo.echo", _QuickAgent())

    with pytest.raises(ValueError, match="already registered"):
        registry.register("demo.echo", _QuickAgent())


async def test_sync_unregister_keeps_old_generation_owned_during_name_reuse() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.02
    old_agent = _GatedAgent()
    registry.register("demo.reused", old_agent)
    old_delegate = asyncio.create_task(
        registry.delegate(agent="demo.reused", task="old", session_id="same")
    )
    await old_agent.invoke_started.wait()

    assert registry.unregister("demo.reused") is old_agent
    replacement = _QuickAgent()
    registry.register("demo.reused", replacement)
    assert (
        await registry.delegate(agent="demo.reused", task="new", session_id="same")
        == "quick"
    )

    old_agent._release.set()
    assert (
        await asyncio.wait_for(old_delegate, timeout=1)
        == "Agent 'demo.reused' unloaded"
    )
    for _ in range(20):
        if old_agent.closed:
            break
        await asyncio.sleep(0)
    assert old_agent.closed
    assert registry._sessions["demo.reused:same"][-1]["content"] == "quick"
    await registry.close()


def test_sync_unregister_without_running_loop_hands_close_ownership_to_caller() -> None:
    registry = AgentRegistry()
    agent = _CountingAgent()
    registry.register("demo.sync", agent)

    assert registry.unregister("demo.sync") is agent
    assert registry._removals == {}
    asyncio.run(agent.close())
    asyncio.run(registry.close())

    assert agent.closed
    assert agent.close_count == 1
    assert registry._removals == {}


async def test_agent_instance_cannot_be_aliased_or_reused_after_close() -> None:
    registry = AgentRegistry()
    agent = _QuickAgent()
    registry.register("demo.one", agent)

    with pytest.raises(ValueError, match="reused or aliased"):
        registry.register("demo.two", agent)

    await registry.unregister_and_drain("demo.one")
    with pytest.raises(ValueError, match="reused or aliased"):
        registry.register("demo.one", agent)


class _NonWeakRefAgent:
    """带 __slots__ 且无 __weakref__ 的实例不可被弱引用。"""

    __slots__ = ("closed",)
    description = "solid"
    tool_definitions: list[dict] = []

    def __init__(self) -> None:
        self.closed = False

    async def invoke(self, state: dict) -> dict:
        return {"messages": [{"role": "assistant", "content": "solid"}]}

    async def close(self) -> None:
        self.closed = True


async def test_non_weakrefable_agent_is_not_permanently_pinned() -> None:
    """不可弱引用的实例不得被注册表永久强持有：活跃期别名被扫描检查拒绝，
    移除完成后 _known_agents 不保留任何强引用且实例可被回收。"""
    registry = AgentRegistry()
    agent = _NonWeakRefAgent()
    registry.register("demo.solid", agent)

    with pytest.raises(ValueError, match="reused or aliased"):
        registry.register("demo.other", agent)

    await registry.unregister_and_drain("demo.solid")
    assert agent.closed
    assert registry._known_agents == {}
    del agent
    gc.collect()


async def test_non_weakrefable_agent_rejected_while_removal_in_flight() -> None:
    """不可弱引用的实例在移除排空进行中仍被扫描检查拒绝（活跃移除持有身份）。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.05
    agent = _NonWeakRefAgent()
    registry.register("demo.solid", agent)
    registry.unregister("demo.solid")

    with pytest.raises(ValueError, match="reused or aliased"):
        registry.register("demo.other", agent)

    await registry.unregister_and_drain("demo.solid")
    assert agent.closed


async def test_unload_queued_same_session_delegates_return_text_not_cancelled() -> None:
    """同 session 并发委托中，排队等待锁的委托被 unregister_and_drain 取消时，
    必须返回友好文本而不是裸 CancelledError。"""
    registry = AgentRegistry()
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    first = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="first", session_id="s1")
    )
    await agent.invoke_started.wait()
    second = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="second", session_id="s1")
    )
    while registry._session_lock_users.get("demo.gate:s1") != 2:
        await asyncio.sleep(0)

    await registry.unregister_and_drain("demo.gate")
    agent._release.set()

    results = await asyncio.gather(first, second)
    assert results == ["Agent 'demo.gate' unloaded", "Agent 'demo.gate' unloaded"]
    assert registry._in_flight == {}
    assert registry._session_lock_users == {}


async def test_drain_cancelled_delegate_returns_friendly_text() -> None:
    """卸载排空主动取消的委托仍返回友好文本（热重载/卸载路径不受影响）。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.05
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.gate", task="go"))
    await agent.invoke_started.wait()
    await registry.unregister_and_drain("demo.gate")
    agent._release.set()

    assert await delegate_task == "Agent 'demo.gate' unloaded"
    assert registry._in_flight == {}


async def test_external_cancel_of_delegate_after_close_propagates() -> None:
    """close 启动（_closed=True）后、排空标记前的外部取消（编排器停机/调用方
    取消）必须传播 CancelledError，而不是被转成友好文本。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 1.0
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.gate", task="go"))
    await agent.invoke_started.wait()
    close_task = asyncio.create_task(registry.close())
    await asyncio.sleep(0)
    delegate_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await delegate_task

    agent._release.set()
    await asyncio.wait_for(close_task, timeout=2)
    assert registry._closed


async def test_close_retries_retired_deferred_close_failure() -> None:
    """退役延迟 close 首次失败时，close() 必须重试直到实例关闭、_retired 清空，
    而不是静默成功。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.02
    agent = _RetiredFailOnceAgent()
    registry.register("demo.retired-fail", agent)
    delegate_task = asyncio.create_task(
        registry.delegate(agent="demo.retired-fail", task="go")
    )
    await agent.invoke_started.wait()
    await registry.unregister_and_drain("demo.retired-fail")
    assert not agent.closed

    agent.release.set()
    await asyncio.wait_for(registry.close(), timeout=2)

    assert agent.closed
    assert agent.close_count == 2
    assert registry._retired == {}
    assert registry._removals == {}
    assert (
        await asyncio.wait_for(delegate_task, timeout=1)
        == "Agent 'demo.retired-fail' unloaded"
    )


async def test_delegate_rejects_whitespace_only_task() -> None:
    """单个委托路径与批量路径一致：空白 task 视为缺失参数。"""
    registry = AgentRegistry()
    registry.register("demo.echo", _QuickAgent())

    assert (
        await registry.delegate(agent="demo.echo", task="   ")
        == "Missing agent or task parameter"
    )
    assert (
        await registry.delegate(agent="demo.echo", task="")
        == "Missing agent or task parameter"
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            {"agent": [], "task": "x"},
            "Invalid agent parameter: expected a string",
        ),
        (
            {"agent": "demo.echo", "task": 1},
            "Invalid task parameter: expected a string",
        ),
        (
            {"agent": "demo.echo", "task": "x", "previous_response": {}},
            "Invalid previous_response parameter: expected a string or None",
        ),
        (
            {"agent": "demo.echo", "task": "x", "context": []},
            "Invalid context parameter: expected a string or None",
        ),
        (
            {"agent": "demo.echo", "task": "x", "session_id": {}},
            "Invalid session_id parameter: expected a string or None",
        ),
    ],
)
async def test_delegate_rejects_invalid_single_argument_types(
    arguments: dict[str, object], expected: str
) -> None:
    registry = AgentRegistry()
    registry.register("demo.echo", _QuickAgent())

    assert await registry.delegate(**arguments) == expected  # type: ignore[arg-type]
    assert registry._in_flight == {}
    await registry.close()


async def test_unregister_after_close_raises() -> None:
    """与 register 一致：注册表关闭后同步 unregister 应报错而不是静默返回。"""
    registry = AgentRegistry()
    await registry.close()

    with pytest.raises(RuntimeError, match="closed"):
        registry.unregister("demo.echo")


async def test_application_shutdown_closes_agent_registry_after_plugin_teardown() -> (
    None
):
    """应用 stop 必须在插件 stop_all 之后关闭共享 AgentRegistry，作为最终清扫。"""
    from neobot_app.runtime.application import NeoBotApplication
    from neobot_contracts.ports.logging import NullLogger

    registry = AgentRegistry()
    agent = _QuickAgent()
    registry.register("demo.app", agent)
    order: list[str] = []
    original_close = registry.close

    async def recorded_close() -> None:
        order.append("close")
        await original_close()

    registry.close = recorded_close  # type: ignore[method-assign]

    class FakePluginRuntime:
        def __init__(self) -> None:
            self.agent_registry = registry

        async def stop_all(self) -> None:
            order.append("stop_all")

    app = object.__new__(NeoBotApplication)
    app.adapter = SimpleNamespace(stop=lambda: asyncio.sleep(0))
    app.file_server = SimpleNamespace(stop=lambda: asyncio.sleep(0))
    app.event_ingress = SimpleNamespace(stop=lambda: None)
    app.chat_stream = None
    app._message_pipeline = None
    app._reply_orchestrator = None
    app._emoji_service = None
    app._logger = NullLogger()
    app._shutdown_event = asyncio.Event()
    app._restart_requested = False
    app._started = True
    app.tts_service = None
    app._bot_detector = None
    app._scheduled_task_manager = None
    app._problem_solver_manager = None
    app._markdown_image_converter = None
    app._plugin_runtime = FakePluginRuntime()
    app._report_service = None
    app._report_task = None
    app._engine = None
    app._vision_provider = None
    app._archive_summary_service = None
    app._browser_lifecycle_manager = None
    app._browser_instance = None
    app._creator_image_service = None
    app._drawing_manager = None
    app._background_coros = []
    app._background_tasks = []
    app._self_heal_manager = None

    await app.stop()

    assert order == ["stop_all", "close"]
    assert agent.closed
    assert registry._closed


async def test_completed_removed_agent_is_not_retained_by_known_tracking() -> None:
    registry = AgentRegistry()
    agent = _QuickAgent()
    agent_ref = weakref.ref(agent)
    registry.register("demo.collectable", agent)
    assert len(registry._known_agents) == 1

    await registry.unregister_and_drain("demo.collectable")
    del agent
    for _ in range(10):
        gc.collect()
        if agent_ref() is None:
            break
        await asyncio.sleep(0)

    assert agent_ref() is None
    assert registry._known_agents == {}


async def test_delegate_timeout_waits_for_cancelled_invoke() -> None:
    """超时后必须真正等待在途任务取消结束，而不是 cancel 完就返回（否则任务泄漏）。"""
    registry = AgentRegistry()
    registry.delegate_timeout_seconds = 0.05
    agent = _SlowCancelAgent()
    registry.register("demo.slow", agent)

    result = await registry.delegate(agent="demo.slow", task="go")

    assert "timed out" in result
    # 修复前：超时后只 cancel 不等待，任务仍在后台运行；修复后返回前任务必须已结束
    assert agent.cancel_processed.is_set()
    assert registry._in_flight == {}


async def test_delegate_outer_cancellation_cancels_invoke() -> None:
    """外层 delegate 任务被取消时，内层 invoke 必须一并取消并等待完成。"""
    registry = AgentRegistry()
    agent = _SlowCancelAgent()
    registry.register("demo.slow", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.slow", task="go"))
    await agent.invoke_started.wait()
    delegate_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await delegate_task

    # 修复前：外层取消时内层 invoke 无人取消，脱离跟踪继续运行
    await asyncio.wait_for(agent.cancel_processed.wait(), timeout=1)
    assert registry._in_flight == {}


class _InvalidStateAgent:
    async def invoke(self, state: dict) -> dict:
        return {"nope": 1}

    async def close(self) -> None:
        pass


async def test_delegate_invalid_agent_state_returns_error() -> None:
    """子 agent 返回不含 messages 的 state 时，delegate 返回错误文本而非 KeyError 崩溃。"""
    registry = AgentRegistry()
    registry.register("demo.bad", _InvalidStateAgent())

    result = await registry.delegate(agent="demo.bad", task="hi")

    assert "invalid state" in result
    assert registry._in_flight == {}
    # 失败结果不应写入会话
    assert "demo.bad:s1" not in registry._sessions


class _MalformedFinalAgent:
    async def invoke(self, state: dict) -> dict:
        return {"messages": [{"role": "user", "content": "not a result"}]}

    async def close(self) -> None:
        pass


async def test_delegate_requires_final_assistant_message_before_writing_history() -> (
    None
):
    registry = AgentRegistry()
    registry.register("demo.bad-final", _MalformedFinalAgent())

    result = await registry.delegate(
        agent="demo.bad-final", task="hi", session_id="failed-session"
    )

    assert "invalid state" in result
    assert registry._sessions == {}
    assert registry._session_locks == {}


class _DelayedRaiseAgent:
    """invoke 延迟抛出异常，用于验证 close 排空时取出已完成任务的异常结果。"""

    def __init__(self) -> None:
        self.invoke_started = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        await asyncio.sleep(0.1)
        raise RuntimeError("boom")

    async def close(self) -> None:
        pass


async def test_close_drain_retrieves_failed_invoke_results(caplog) -> None:
    """close 排空时对已完成（含异常）的任务统一收集结果，
    避免异常未被取出而触发 "Task exception was never retrieved" 警告。"""
    import gc
    import logging

    registry = AgentRegistry()
    registry.drain_timeout_seconds = 2.0
    agent = _DelayedRaiseAgent()
    registry.register("demo.boom", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.boom", task="go"))
    await agent.invoke_started.wait()

    with caplog.at_level(logging.WARNING, logger="asyncio"):
        await registry.close()
        try:
            await delegate_task
        except RuntimeError:
            pass
        gc.collect()

    assert registry._in_flight == {}
    assert not any(
        "Task exception was never retrieved" in record.message
        for record in caplog.records
    )


async def test_unregister_and_drain_removes_registration_sessions_and_blocks_new_calls() -> (
    None
):
    """unregister_and_drain 必须关闭实例、清理该 Agent 的会话与锁，并阻止后续新委托。"""
    registry = AgentRegistry()
    agent = _QuickAgent()
    registry.register("demo.echo", agent)

    await registry.delegate(agent="demo.echo", task="first", session_id="s1")
    removed = await registry.unregister_and_drain("demo.echo")

    assert removed is agent
    assert agent.closed
    assert registry.names == []
    assert "demo.echo:s1" not in registry._sessions
    assert "demo.echo:s1" not in registry._session_locks
    assert registry._in_flight == {}
    # 已被移除的 agent 拒绝新委托
    result = await registry.delegate(agent="demo.echo", task="hi")
    assert "not found" in result


async def test_unregister_and_drain_cancels_in_flight_only_for_that_agent() -> None:
    """卸载单个 Agent：只取消其自己的在途任务并关闭其实例，不影响其他 Agent 的任务。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.2
    slow = _HangingAgent()
    other = _HangingAgent()
    registry.register("demo.slow", slow)
    registry.register("demo.other", other)

    slow_task = asyncio.create_task(registry.delegate(agent="demo.slow", task="go"))
    other_task = asyncio.create_task(registry.delegate(agent="demo.other", task="go"))
    await slow.invoke_started.wait()
    await other.invoke_started.wait()

    await registry.unregister_and_drain("demo.slow")

    assert slow.closed
    assert not other.closed
    assert "demo.slow" not in registry._in_flight
    # 被卸载 agent 的在途委托因取消而结束，返回友好文本而非 CancelledError
    # （app 侧 except Exception 不捕获 CancelledError，会静默断回复）
    assert await slow_task == "Agent 'demo.slow' unloaded"
    # 其他 agent 的在途委托不受影响，正常完成
    other._release.set()
    assert await other_task == "done"
    await registry.close()


async def test_unregister_and_drain_waits_for_cancelled_invoke() -> None:
    """unregister_and_drain 超时取消后必须等待在途任务真正结束，任务不泄漏。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.05
    agent = _SlowCancelAgent()
    registry.register("demo.slow", agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.slow", task="go"))
    await agent.invoke_started.wait()

    await registry.unregister_and_drain("demo.slow")

    assert agent.closed
    assert agent.cancel_processed.is_set()
    assert registry._in_flight == {}
    assert await delegate_task == "Agent 'demo.slow' unloaded"


async def test_cancelled_unregister_keeps_internal_drain_owned_and_retryable() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.1
    agent = _SlowCancelAgent()
    registry.register("demo.slow", agent)
    delegate_task = asyncio.create_task(registry.delegate(agent="demo.slow", task="go"))
    await agent.invoke_started.wait()

    unload = asyncio.create_task(registry.unregister_and_drain("demo.slow"))
    await asyncio.sleep(0)
    unload.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unload

    assert await registry.unregister_and_drain("demo.slow") is agent
    assert agent.closed
    assert await delegate_task == "Agent 'demo.slow' unloaded"


async def test_unregister_and_drain_while_replaced_returns_unloaded_text() -> None:
    """卸载竞态：invoke 在途时 agent 被 unregister_and_drain 取消，即使同名单
    已注册新实例（热重载），delegate 也应返回友好文本而非抛出 CancelledError。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.2
    old_agent = _HangingAgent()
    registry.register("demo.gate", old_agent)

    delegate_task = asyncio.create_task(registry.delegate(agent="demo.gate", task="go"))
    await old_agent.invoke_started.wait()
    await registry.unregister_and_drain("demo.gate")
    # 热重载：同名单注册新实例
    registry.register("demo.gate", _QuickAgent())

    assert await delegate_task == "Agent 'demo.gate' unloaded"
    assert registry._in_flight == {}
    await registry.close()


async def test_unregister_prevents_in_flight_delegate_session_resurrection() -> None:
    """委托进行中卸载（同步 unregister 清会话）后，在途 invoke 完成不得写回复活会话。

    修复前：invoke 完成后无条件写回 _sessions，热重载后新 Agent 会继承旧历史。
    """
    registry = AgentRegistry()
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    delegate_task = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="go", session_id="s1")
    )
    await agent.invoke_started.wait()
    # 委托在途时卸载：会话与锁被清除
    registry.unregister("demo.gate")
    assert "demo.gate:s1" not in registry._sessions

    # The old result may complete before the scheduled drain runs, but cannot write a session.
    agent._release.set()
    result = await delegate_task

    assert result == "reply-1"
    assert "demo.gate:s1" not in registry._sessions


async def test_unregister_then_reload_does_not_inherit_old_session() -> None:
    """同名单热重载后（新实例注册），旧实例在途委托的会话不得写进新实例名下。"""
    registry = AgentRegistry()
    old_agent = _GatedAgent()
    registry.register("demo.gate", old_agent)

    delegate_task = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="go", session_id="s1")
    )
    await old_agent.invoke_started.wait()
    registry.unregister("demo.gate")

    # 热重载：同名单注册新实例
    new_agent = _QuickAgent()
    registry.register("demo.gate", new_agent)
    old_agent._release.set()
    await delegate_task

    # 新 Agent 名下没有任何旧会话
    assert "demo.gate:s1" not in registry._sessions
    await registry.close()


async def test_concurrent_delegates_same_session_preserve_history() -> None:
    """同一 agent+session 的并发委托必须串行读写会话，最终包含两条 user+assistant
    记录而非互相覆盖。"""
    registry = AgentRegistry()
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    t1 = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="first", session_id="s1")
    )
    await agent.invoke_started.wait()
    agent.invoke_started.clear()
    t2 = asyncio.create_task(
        registry.delegate(agent="demo.gate", task="second", session_id="s1")
    )
    # 同 session 加锁后，第二个委托必须等待，不会进入 invoke
    await asyncio.sleep(0.05)
    assert agent.invoke_count == 1
    agent._release.set()

    results = await asyncio.gather(t1, t2)
    assert results == ["reply-1", "reply-2"]

    messages = registry._sessions["demo.gate:s1"]
    users = [m for m in messages if m["role"] == "user"]
    assistants = [m for m in messages if m["role"] == "assistant"]
    assert [m["content"] for m in users] == ["first", "second"]
    assert [m["content"] for m in assistants] == ["reply-1", "reply-2"]
    await registry.close()


async def test_delegates_without_session_run_in_parallel() -> None:
    """无 session_id 的委托不加锁，保持并行进入 invoke。"""
    registry = AgentRegistry()
    agent = _GatedAgent()
    registry.register("demo.gate", agent)

    t1 = asyncio.create_task(registry.delegate(agent="demo.gate", task="first"))
    await agent.invoke_started.wait()
    agent.invoke_started.clear()
    t2 = asyncio.create_task(registry.delegate(agent="demo.gate", task="second"))
    await agent.invoke_started.wait()

    assert agent.invoke_count == 2
    agent._release.set()
    await asyncio.gather(t1, t2)


class _StubbornAgent:
    """invoke 忽略第一次取消（顽固），第二次取消才真正退出。

    用于验证：单次取消无效时卸载必须能继续推进（第二重取消/超时 detach），
    同时测试结束时任务能干净退出，不阻塞事件循环关闭。
    """

    def __init__(self) -> None:
        self.closed = False
        self.invoke_started = asyncio.Event()
        self._cancels = 0

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self._cancels += 1
                if self._cancels >= 2:
                    raise
                continue

    async def close(self) -> None:
        self.closed = True


async def test_unregister_and_drain_survives_stubborn_agent() -> None:
    """顽固 agent（忽略第一次取消）不得让 unregister_and_drain 永久挂死。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.1
    agent = _StubbornAgent()
    registry.register("demo.stubborn", agent)

    delegate_task = asyncio.create_task(
        registry.delegate(agent="demo.stubborn", task="go")
    )
    await agent.invoke_started.wait()

    result = await asyncio.wait_for(
        registry.unregister_and_drain("demo.stubborn"), timeout=1.0
    )
    assert result is agent
    assert agent.closed
    assert registry.names == []
    # 第二次取消生效：delegate 收到 unloaded 文本而非挂死
    assert await delegate_task == "Agent 'demo.stubborn' unloaded"
    assert registry._in_flight == {}


async def test_delegate_timeout_survives_stubborn_agent() -> None:
    """顽固 agent 超时路径不得挂死 delegate：第二重取消后返回超时文本。"""
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.1
    registry.delegate_timeout_seconds = 0.1
    agent = _StubbornAgent()
    registry.register("demo.stubborn", agent)

    result = await asyncio.wait_for(
        registry.delegate(agent="demo.stubborn", task="go"), timeout=1.0
    )
    assert "timed out" in result
    await registry.close()


class _ForeverStubbornAgent:
    def __init__(self) -> None:
        self.closed = False
        self.close_count = 0
        self.invoke_started = asyncio.Event()
        self.release = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                continue
        return {"messages": [{"role": "assistant", "content": "released"}]}

    async def close(self) -> None:
        self.close_count += 1
        self.closed = True


class _RetiredRaceAgent:
    def __init__(self) -> None:
        self.closed = False
        self.close_count = 0
        self.active_closes = 0
        self.max_active_closes = 0
        self.invoke_started = asyncio.Event()
        self.release_invoke = asyncio.Event()
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def invoke(self, state: dict) -> dict:
        self.invoke_started.set()
        while not self.release_invoke.is_set():
            try:
                await self.release_invoke.wait()
            except asyncio.CancelledError:
                continue
        return {"messages": [{"role": "assistant", "content": "released"}]}

    async def close(self) -> None:
        self.close_count += 1
        self.active_closes += 1
        self.max_active_closes = max(self.max_active_closes, self.active_closes)
        self.close_started.set()
        try:
            if self.close_count == 1:
                await self.release_close.wait()
                raise RuntimeError("transient retired close failure")
            self.closed = True
        finally:
            self.active_closes -= 1


async def test_forever_stubborn_invoke_retains_owner_and_defers_close() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.02
    agent = _ForeverStubbornAgent()
    registry.register("demo.forever", agent)
    delegate_task = asyncio.create_task(
        registry.delegate(agent="demo.forever", task="go")
    )
    await agent.invoke_started.wait()

    assert (
        await asyncio.wait_for(registry.unregister_and_drain("demo.forever"), timeout=1)
        is agent
    )
    assert not agent.closed
    assert any(
        removal.registration.agent is agent for removal in registry._retired.values()
    )

    agent.release.set()
    assert (
        await asyncio.wait_for(delegate_task, timeout=1)
        == "Agent 'demo.forever' unloaded"
    )
    for _ in range(20):
        if agent.closed and not registry._retired:
            break
        await asyncio.sleep(0)
    assert agent.close_count == 1
    assert registry._retired == {}


async def test_retired_callback_owns_completion_until_transient_failure() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.01
    registry.close_retry_budget = 1
    agent = _RetiredRaceAgent()
    registry.register("demo.retired-race", agent)
    delegate = asyncio.create_task(
        registry.delegate(agent="demo.retired-race", task="go")
    )
    await asyncio.wait_for(agent.invoke_started.wait(), timeout=1)
    await asyncio.wait_for(
        registry.unregister_and_drain("demo.retired-race"), timeout=1
    )
    removal = next(iter(registry._removals.values()))
    shutdown: asyncio.Task | None = None

    try:
        agent.release_invoke.set()
        await asyncio.wait_for(agent.close_started.wait(), timeout=1)
        while removal.operation is not None:
            await asyncio.sleep(0)
        assert (
            await asyncio.wait_for(
                registry.unregister_and_drain("demo.retired-race"), timeout=0.1
            )
            is agent
        )
        assert removal.operation is None

        shutdown = asyncio.create_task(registry.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert removal.finishing
        assert removal.operation is None

        agent.release_close.set()
        await asyncio.wait_for(shutdown, timeout=1)

        assert agent.closed
        assert agent.close_count == 2
        assert agent.max_active_closes == 1
        assert registry._retired == {}
        assert registry._removals == {}
        assert await asyncio.wait_for(delegate, timeout=1) == (
            "Agent 'demo.retired-race' unloaded"
        )
    finally:
        agent.release_invoke.set()
        agent.release_close.set()
        if shutdown is not None:
            await asyncio.gather(shutdown, return_exceptions=True)
        await asyncio.gather(delegate, return_exceptions=True)


async def test_many_failed_unique_sessions_do_not_grow_locks() -> None:
    registry = AgentRegistry()
    registry.register("demo.bad", _InvalidStateAgent())

    for i in range(2_000):
        result = await registry.delegate(
            agent="demo.bad", task="x", session_id=f"bad-{i}"
        )
        assert "invalid state" in result

    assert registry._sessions == {}
    assert registry._session_locks == {}
    assert registry._session_lock_users == {}


async def test_session_and_lock_counts_remain_bounded_after_eviction() -> None:
    registry = AgentRegistry()
    registry.max_sessions_per_agent = 10
    registry.register("demo.quick", _QuickAgent())

    for i in range(250):
        await registry.delegate(agent="demo.quick", task="x", session_id=f"ok-{i}")

    assert len(registry._sessions) == 10
    assert len(registry._session_locks) == 10
    assert registry._session_lock_users == {}
    await registry.close()


class _CancelledAgent:
    async def invoke(self, state: dict) -> dict:
        raise asyncio.CancelledError

    async def close(self) -> None:
        pass


async def test_batch_delegation_renders_child_cancelled_error() -> None:
    registry = AgentRegistry()
    registry.register("demo.cancelled", _CancelledAgent())

    result = await registry.delegate(tasks=[{"agent": "demo.cancelled", "task": "x"}])

    assert "Agent failed: CancelledError" in result
    await registry.close()


async def test_malformed_batch_is_rejected_before_any_coroutine_is_created() -> None:
    registry = AgentRegistry()
    agent = _QuickAgent()
    registry.register("demo.quick", agent)

    expected = "Invalid batch tasks: each task must include non-empty 'agent' and 'task' strings"
    assert await registry.delegate(tasks=[{"agent": "demo.quick"}]) == expected
    assert await registry.delegate(tasks=[None]) == expected  # type: ignore[list-item]
    assert registry._in_flight == {}
    await registry.close()


async def test_batch_rejects_invalid_optional_argument_types_consistently() -> None:
    registry = AgentRegistry()
    registry.register("demo.quick", _QuickAgent())

    assert await registry.delegate(
        tasks=[
            {
                "agent": "demo.quick",
                "task": "x",
                "previous_response": 1,
            }
        ]
    ) == (
        "Invalid batch task at index 0: "
        "Invalid previous_response parameter: expected a string or None"
    )
    assert await registry.delegate(
        tasks=[{"agent": "demo.quick", "task": "x", "session_id": []}]
    ) == (
        "Invalid batch task at index 0: "
        "Invalid session_id parameter: expected a string or None"
    )
    assert registry._in_flight == {}
    await registry.close()


async def test_unregister_close_failure_is_reported_and_retryable() -> None:
    registry = AgentRegistry()
    agent = _FailingCloseAgent()
    registry.register("demo.flaky-close", agent)

    with pytest.raises(RuntimeError, match="close failed"):
        await registry.unregister_and_drain("demo.flaky-close")
    assert agent.close_count == 1
    assert await registry.unregister_and_drain("demo.flaky-close") is agent
    assert agent.close_count == 2
    assert agent.closed


async def test_close_reports_permanent_failure_with_only_done_removal_tasks() -> None:
    registry = AgentRegistry()
    registry.close_retry_budget = 1
    agent = _PermanentCloseAgent()
    registry.register("demo.permanent-close", agent)

    with pytest.raises(RuntimeError, match="permanent close failure"):
        await registry.unregister_and_drain("demo.permanent-close")
    removal = next(iter(registry._removals.values()))
    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    removal.tasks.add(completed)

    with pytest.raises(RuntimeError, match="permanent close failure") as caught:
        await registry.close()

    assert agent.close_count == 2
    assert removal.tasks == set()
    assert isinstance(caught.value.__cause__, BaseExceptionGroup)
    assert any(
        "permanent close failure" in str(error)
        for error in caught.value.__cause__.exceptions
    )


async def test_close_surfaces_drain_error_with_pending_tasks() -> None:
    registry = AgentRegistry()
    registry.close_retry_budget = 1
    agent = _HangingAgent()
    registry.register("demo.drain-error", agent)
    delegate = asyncio.create_task(
        registry.delegate(agent="demo.drain-error", task="go")
    )
    await asyncio.wait_for(agent.invoke_started.wait(), timeout=1)
    original_drain = registry._drain_removed_agent
    attempts = 0

    async def failing_drain(removal, timeout):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("drain root failure")

    registry._drain_removed_agent = failing_drain  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="drain root failure") as caught:
            await registry.close()

        assert attempts == 2
        assert isinstance(caught.value.__cause__, BaseExceptionGroup)
        assert any(
            "drain root failure" in str(error)
            for error in caught.value.__cause__.exceptions
        )
    finally:
        registry._drain_removed_agent = original_drain  # type: ignore[method-assign]
        agent._release.set()
        await asyncio.gather(delegate, return_exceptions=True)
        await registry.unregister_and_drain("demo.drain-error")

    assert agent.closed
    assert registry._removals == {}


async def test_close_retry_budget_is_persistent_across_calls() -> None:
    registry = AgentRegistry()
    registry.close_retry_budget = 2
    agent = _PermanentCloseAgent()
    registry.register("demo.bounded-close", agent)

    with pytest.raises(RuntimeError, match="permanent close failure"):
        await registry.close()
    assert agent.close_count == 3

    for _ in range(3):
        with pytest.raises(RuntimeError, match="permanent close failure"):
            await registry.close()
    assert agent.close_count == 3


async def test_close_timeout_survives_and_later_success_clears_pending() -> None:
    registry = AgentRegistry()
    registry.close_wait_timeout_seconds = 0.02
    agent = _TimeoutCloseAgent()
    registry.register("demo.timeout-close", agent)

    first_close = asyncio.create_task(registry.close())
    await asyncio.wait_for(agent.close_started.wait(), timeout=1)
    with pytest.raises(RuntimeError, match="close incomplete"):
        await first_close

    assert registry._close_pending
    assert agent.cancel_count == 0
    assert agent.close_count == 1

    agent.release_close.set()
    await asyncio.wait_for(registry.close(), timeout=1)

    assert agent.closed
    assert agent.close_count == 1
    assert not registry._close_pending
    assert registry._removals == {}


async def test_close_budget_timeout_does_not_cancel_in_flight_drain() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.01
    registry.close_wait_timeout_seconds = 0.03
    agent = _SlowDrainCleanupAgent()
    registry.register("demo.slow-drain", agent)
    delegate = asyncio.create_task(
        registry.delegate(agent="demo.slow-drain", task="go")
    )
    await asyncio.wait_for(agent.invoke_started.wait(), timeout=1)

    try:
        with pytest.raises(RuntimeError, match="close incomplete"):
            await registry.close()
        await asyncio.wait_for(agent.cleanup_started.wait(), timeout=1)
        removal = next(iter(registry._removals.values()))
        assert removal.operation is not None
        assert not removal.operation.done()
        assert not removal.operation.cancelled()

        agent.release_cleanup.set()
        await asyncio.wait_for(registry.close(), timeout=1)

        assert agent.closed
        assert await asyncio.wait_for(delegate, timeout=1) == (
            "Agent 'demo.slow-drain' cancelled: registry closed"
        )
        assert registry._removals == {}
    finally:
        agent.release_cleanup.set()
        await asyncio.gather(delegate, return_exceptions=True)


async def test_callback_created_close_task_is_owned_by_registry_shutdown() -> None:
    registry = AgentRegistry()
    registry.drain_timeout_seconds = 0.01
    agent = _GatedCloseAgent()
    registry.register("demo.callback", agent)
    delegate = asyncio.create_task(registry.delegate(agent="demo.callback", task="go"))
    close_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(agent.invoke_started.wait(), timeout=1)
        await asyncio.wait_for(
            registry.unregister_and_drain("demo.callback"), timeout=1
        )

        agent.release_invoke.set()
        await asyncio.wait_for(agent.close_started.wait(), timeout=1)
        close_task = asyncio.create_task(registry.close())
        await asyncio.sleep(0)
        assert not close_task.done()

        agent.release_close.set()
        await asyncio.wait_for(close_task, timeout=1)
        assert agent.closed
        assert registry._callback_tasks == set()
        await asyncio.wait_for(delegate, timeout=1)
    finally:
        agent.release_invoke.set()
        agent.release_close.set()
        if close_task is not None:
            await asyncio.gather(close_task, return_exceptions=True)
        await asyncio.gather(delegate, return_exceptions=True)


async def test_concurrent_close_and_unregister_close_agent_once() -> None:
    registry = AgentRegistry()
    agent = _CountingAgent()
    registry.register("demo.count", agent)

    removed, _ = await asyncio.gather(
        registry.unregister_and_drain("demo.count"), registry.close()
    )

    assert removed is agent
    assert agent.close_count == 1
    await registry.close()
    assert agent.close_count == 1


async def test_sessions_trimmed_per_agent() -> None:
    """每个 Agent 的会话数超过上限后按最旧淘汰。"""
    registry = AgentRegistry()
    registry.max_sessions_per_agent = 3
    agent = _QuickAgent()
    registry.register("demo.trim", agent)

    for i in range(5):
        await registry.delegate(agent="demo.trim", task=f"t{i}", session_id=f"s{i}")

    keys = [k for k in registry._sessions if k.startswith("demo.trim:")]
    assert keys == ["demo.trim:s2", "demo.trim:s3", "demo.trim:s4"]
    assert registry._session_locks
    await registry.close()
    await registry.close()
