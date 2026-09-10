"""命令同步回复被拒时，「回复中」标记必须回滚。

_start_command_sync_reply 先把 queue_key 放进 _replying_queues，再靠
on_reply_done 回调移除；而 start_reply 在「编排器已关闭 / 同会话管线在跑 /
冷却中」时返回 None 且不会调用回调——标记就此永久留下，该会话的命令结果
再也投递不出去，后续消息也被当作「回复中」。
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


def test_marker_rolled_back_when_start_reply_declined() -> None:
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
    assert any("回滚" in msg for msg, _ in pipeline._logger.debugs)


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
