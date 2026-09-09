"""ProblemSolverManager 后台任务注册、shutdown 取消与异常兜底测试。"""

from __future__ import annotations

import asyncio
import json

from neobot_app.agents.problem_solver import (
    _SOLUTION_RESULT,
    ProblemSolverAgentConfig,
    ProblemSolverManager,
)


# ── 回归: provider 不可用时降级，不抛 AttributeError ──


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **_kwargs) -> None:
        self.warnings.append(message)


def test_build_problem_solver_agent_returns_none_without_provider() -> None:
    """provider 为 None（主模型与解题模型都不可用）时降级返回 None。"""
    from neobot_app.agents.problem_solver import build_problem_solver_agent

    logger = _RecordingLogger()

    agent = build_problem_solver_agent(None, logger=logger)

    assert agent is None
    assert logger.warnings and "provider 不可用" in logger.warnings[0]


class _FakeHub:
    """假通知中心：publish 返回可配置的 started，记录调用。"""

    def __init__(self, started: bool = False) -> None:
        self.started = started
        self.published: list[dict] = []
        self.orchestrator = None

    def set_orchestrator(self, orchestrator) -> None:
        self.orchestrator = orchestrator

    async def publish(self, **kwargs) -> bool:
        self.published.append(kwargs)
        return self.started

    async def poll(self, pipeline_key, source=None):
        return None

    def get_pipeline_status(self, pipeline_key):
        return {"background_notifications_by_source": {}}


class _FakeSolverAgent:
    """假解题 Agent：可提交解答、可抛错、可阻塞。"""

    def __init__(
        self,
        *,
        solution: str = "",
        raise_exc: Exception | None = None,
        block: bool = False,
    ) -> None:
        self.solution = solution
        self.raise_exc = raise_exc
        self.block = block
        self.release = asyncio.Event()
        self.invocations = 0
        self.close_calls = 0

    async def _invoke_direct(self, state):
        self.invocations += 1
        if self.block:
            await self.release.wait()
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.solution:
            _SOLUTION_RESULT.set(self.solution)
        return {"messages": []}

    async def close(self) -> None:
        self.close_calls += 1


def _make_manager(*, agent=None, hub=None, **overrides) -> ProblemSolverManager:
    config = ProblemSolverAgentConfig(startup_grace_seconds=0.01, **overrides)
    manager = ProblemSolverManager(config=config, notification_hub=hub)
    if agent is not None:
        manager.set_agent(agent)
    return manager


def _submit_kwargs(**overrides) -> dict:
    kwargs = {
        "pipeline_key": "group:1",
        "conversation_kind": "group",
        "conversation_id": "1",
        "question": "证明哥德巴赫猜想",
    }
    kwargs.update(overrides)
    return kwargs


async def _slow_noop() -> None:
    await asyncio.sleep(0.05)


async def test_spawn_bg_task_registers_and_discards_on_done() -> None:
    """_spawn_bg_task 注册的任务在完成回调后必须从 _bg_tasks 中移除。"""
    manager = _make_manager(agent=_FakeSolverAgent())

    task = manager._spawn_bg_task(_slow_noop())
    assert task in manager._bg_tasks

    await task
    await asyncio.sleep(0)
    assert manager._bg_tasks == set()


async def test_concurrent_spawn_registers_both_tasks() -> None:
    """并发注册两个后台任务必须互不干扰，完成后都被 discard。"""
    manager = _make_manager(agent=_FakeSolverAgent())

    async def _spawn() -> asyncio.Task:
        task = manager._spawn_bg_task(_slow_noop())
        await asyncio.sleep(0)
        return task

    t1, t2 = await asyncio.gather(_spawn(), _spawn())
    assert len(manager._bg_tasks) == 2

    await asyncio.gather(t1, t2)
    await asyncio.sleep(0)
    assert manager._bg_tasks == set()


async def test_shutdown_cancels_running_solve_and_marks_failed() -> None:
    """shutdown() 必须取消进行中的解题任务，并将其标记为 failed。"""
    agent = _FakeSolverAgent(block=True)
    manager = _make_manager(agent=agent)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["status"] == "solving"
    task = next(iter(manager._tasks.values()))
    bg = next(iter(manager._bg_tasks))
    assert not bg.done()

    await manager.shutdown()
    assert bg.cancelled()
    assert task.status == "failed"
    assert task.error == "系统关闭，任务被取消"
    assert manager._bg_tasks == set()
    assert manager._tasks == {}


async def test_shutdown_is_idempotent() -> None:
    """连续调用 shutdown() 不得抛错，状态保持已清理。"""
    agent = _FakeSolverAgent()
    manager = _make_manager(agent=agent)

    await manager.shutdown()
    assert manager._bg_tasks == set()
    assert manager._tasks == {}

    await manager.shutdown()
    assert manager._bg_tasks == set()
    assert manager._tasks == {}
    assert manager._notification_queues == {}
    assert agent.close_calls == 1
    assert manager._agent is None


async def test_run_solve_exception_marks_failed_and_notifies() -> None:
    """解题 Agent 抛错时任务必须标记 failed 并推送失败通知。"""
    hub = _FakeHub(started=True)
    agent = _FakeSolverAgent(raise_exc=RuntimeError("解题器爆炸"))
    manager = _make_manager(agent=agent, hub=hub)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["ok"] is False
    task = next(iter(manager._tasks.values()))
    assert task.status == "failed"
    assert "解题器爆炸" in task.error
    assert any("解题任务失败" in p["content"] for p in hub.published)
    await manager.shutdown()


async def test_run_solve_without_solution_falls_back_to_failed() -> None:
    """Agent 未提交解答时须重新唤起一次，仍无解答则任务失败。"""
    agent = _FakeSolverAgent(solution="")
    manager = _make_manager(agent=agent)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["ok"] is False
    task = next(iter(manager._tasks.values()))
    assert task.status == "failed"
    assert "重新唤起" in task.error
    assert agent.invocations == 2


async def test_submit_requires_configured_agent() -> None:
    """未配置解题 Agent 时 submit 必须返回错误且不产生任务。"""
    manager = _make_manager(agent=None)

    result = json.loads(await manager.submit(**_submit_kwargs()))
    assert result["ok"] is False
    assert "未配置" in result["error"]
    assert manager._tasks == {}


async def test_submit_returns_busy_when_active_solve() -> None:
    """存在 solving 状态任务时重复提交必须返回 busy。"""
    agent = _FakeSolverAgent(block=True)
    manager = _make_manager(agent=agent)

    first = json.loads(await manager.submit(**_submit_kwargs()))
    assert first["status"] == "solving"

    second = json.loads(await manager.submit(**_submit_kwargs()))
    assert second["status"] == "busy"

    agent.release.set()
    await manager.shutdown()
