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
