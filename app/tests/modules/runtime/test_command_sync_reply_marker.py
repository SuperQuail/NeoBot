"""命令同步回复被拒时，「回复中」标记不能被误删。

标记 _replying_queues 是按 queue_key 共享的裸 set，而 start_reply 拒绝的常见
原因恰恰是「同会话已有管线在跑」——那种情况下标记属于**另一条仍在运行的管线**。
旧实现在被拒时无条件 discard，会删掉那条管线的标记，破坏它的分流守卫。
正确语义是「启动成功后才打标记」，由该管线自己的 on_reply_done 清除。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.runtime.event_pipeline import EventPipeline


class _RecordingLogger:
    def __init__(self) -> None:
        self.debugs: list[tuple[str, dict]] = []

    def warning(self, message: str, **kw) -> None:
        pass

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        self.debugs.append((message, kw))

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


class _StubOrchestrator:
    def __init__(self, *, started: object) -> None:
        self.started = started
        self.calls: list[dict] = []

    def start_reply(self, **kwargs):
        self.calls.append(kwargs)
        return self.started


class _StubQueue:
    def get_last_message_id(self, queue_key: str):
        return 42


def _make_pipeline(orchestrator) -> EventPipeline:
    pipeline = EventPipeline.__new__(EventPipeline)
    pipeline._reply_orchestrator = orchestrator
    pipeline._replying_queues = set()
    pipeline._logger = _RecordingLogger()
    return pipeline


def test_marker_not_set_when_start_reply_declined() -> None:
    orchestrator = _StubOrchestrator(started=None)
    pipeline = _make_pipeline(orchestrator)

    pipeline._start_command_sync_reply(
        message=SimpleNamespace(),
        queue=_StubQueue(),
        queue_key="group:1",
        background="cmd output",
    )

    assert pipeline._replying_queues == set()
    assert len(orchestrator.calls) == 1


def test_running_pipeline_marker_survives_rejected_command_sync_reply() -> None:
    """同会话已有管线在跑时，它的标记必须原样保留。"""
    orchestrator = _StubOrchestrator(started=None)
    pipeline = _make_pipeline(orchestrator)
    pipeline._replying_queues.add("group:1")

    pipeline._start_command_sync_reply(
        message=SimpleNamespace(),
        queue=_StubQueue(),
        queue_key="group:1",
        background="cmd output",
    )

    assert pipeline._replying_queues == {"group:1"}


def test_marker_kept_when_pipeline_started() -> None:
    """管线正常启动时标记保留，等 on_reply_done 回调移除。"""
    orchestrator = _StubOrchestrator(started=SimpleNamespace())
    pipeline = _make_pipeline(orchestrator)

    pipeline._start_command_sync_reply(
        message=SimpleNamespace(),
        queue=_StubQueue(),
        queue_key="group:2",
        background="cmd output",
    )

    assert pipeline._replying_queues == {"group:2"}
    callback = orchestrator.calls[0]["on_reply_done"]
    assert callback is not None


async def test_on_reply_done_removes_marker() -> None:
    orchestrator = _StubOrchestrator(started=SimpleNamespace())
    pipeline = _make_pipeline(orchestrator)
    pipeline._post_reply_willing = {}
    pipeline._config = None

    pipeline._start_command_sync_reply(
        message=SimpleNamespace(),
        queue=_StubQueue(),
        queue_key="group:3",
        background="cmd output",
    )
    await orchestrator.calls[0]["on_reply_done"]()

    assert pipeline._replying_queues == set()
