"""回复工具执行器必须随管线释放（旧实现只增不减）。

每次 agent 模式回复都会 build_reply_toolset 并 `_tool_executors.add(executor)`，
而 _cleanup（done 回调）从不清除它、只有进程关停时才 clear()：执行器持有该轮
完整对话历史、技能 token 与会话任务信息，等于每个回复事件泄漏一份。
"""

from __future__ import annotations

import asyncio

from neobot_app.reply.orchestrator import ReplyOrchestrator


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, message: str, **kw) -> None:
        self.warnings.append((message, kw))

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        pass

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


class _Executor:
    def __init__(self, *, fail: bool = False) -> None:
        self.closed = 0
        self.fail = fail

    async def close(self) -> None:
        self.closed += 1
        if self.fail:
            raise RuntimeError("close boom")


class _SyncCloseExecutor:
    """close() 不是协程的执行器：释放失败不能冒泡到 done 回调。"""

    def close(self) -> None:  # type: ignore[no-untyped-def]
        pass


class _SessionExecutor:
    """带在途会话工具的执行器：后台工作必须活到自然完成，然后才关闭。"""

    def __init__(self, delay: float = 0.01) -> None:
        self.events: list[str] = []
        self._delay = delay
        self.session = asyncio.create_task(self._run_session())

    async def _run_session(self) -> None:
        await asyncio.sleep(self._delay)
        self.events.append("session-completed")

    async def drain_sessions(self) -> None:
        await asyncio.gather(self.session, return_exceptions=True)

    async def close(self) -> None:
        if not self.session.done():
            self.session.cancel()
            self.events.append("session-cancelled")
        self.events.append("closed")


def _make_orchestrator() -> ReplyOrchestrator:
    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orchestrator._tool_executors = {}
    orchestrator._callback_tasks = set()
    orchestrator._logger = _RecordingLogger()
    return orchestrator


async def test_release_closes_and_drops_executor() -> None:
    orchestrator = _make_orchestrator()
    executor = _Executor()
    orchestrator._tool_executors["e1"] = executor

    orchestrator._release_executor("e1")
    await asyncio.sleep(0)  # 让 close 协程跑完
    await asyncio.sleep(0)  # 让 done 回调把任务从集合里摘掉

    assert executor.closed == 1
    assert orchestrator._tool_executors == {}
    assert orchestrator._callback_tasks == set()


async def test_release_is_idempotent_for_unknown_event() -> None:
    orchestrator = _make_orchestrator()

    orchestrator._release_executor("missing")  # 不应抛异常
    await asyncio.sleep(0)

    assert orchestrator._tool_executors == {}


async def test_release_logs_close_failure() -> None:
    orchestrator = _make_orchestrator()
    orchestrator._tool_executors["e2"] = _Executor(fail=True)

    orchestrator._release_executor("e2")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert orchestrator._tool_executors == {}
    assert any("释放失败" in msg for msg, _ in orchestrator._logger.warnings)


async def test_many_replies_do_not_accumulate_executors() -> None:
    """模拟多轮回复：每次注册 + 释放后不得残留。"""
    orchestrator = _make_orchestrator()

    for index in range(5):
        event_id = f"e{index}"
        orchestrator._tool_executors[event_id] = _Executor()
        orchestrator._release_executor(event_id)
    await asyncio.sleep(0)

    assert orchestrator._tool_executors == {}


async def test_release_does_not_cancel_inflight_session_tools() -> None:
    """回复结束释放执行器时，在途会话工具必须跑完（而不是被取消）。

    会话工具（download__url / parse_image 等）的契约是「后台执行，完成后自动
    通知」，活过本轮回复；直接 close() 会把它们连同通知一起杀掉。
    """
    orchestrator = _make_orchestrator()
    executor = _SessionExecutor(delay=0.01)
    orchestrator._tool_executors["e9"] = executor

    orchestrator._release_executor("e9")
    await asyncio.sleep(0.05)

    assert executor.events == ["session-completed", "closed"]
    assert orchestrator._tool_executors == {}


async def test_release_survives_non_awaitable_close() -> None:
    """close() 不是协程时只记日志，不能让 done 回调抛异常。"""
    orchestrator = _make_orchestrator()
    orchestrator._tool_executors["e10"] = _SyncCloseExecutor()

    orchestrator._release_executor("e10")  # 不应抛异常
    for _ in range(3):
        await asyncio.sleep(0)  # 让 close 任务失败并由 done 回调记录

    assert orchestrator._tool_executors == {}
    assert any("释放失败" in msg for msg, _ in orchestrator._logger.warnings)
