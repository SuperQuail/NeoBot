"""图片意愿待处理队列：等待解析失败时不得让消息永久滞留。

含图片的消息会先进 _pending_image_willing 等图片解析完成再算意愿。原实现在
等待抛异常时直接冒出，pending 列表既不被取出也不被处理：这些消息再也不会
触发回复，字典条目也永久留在内存里。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.runtime.event_pipeline import EventPipeline


class _FailingParseService:
    def __init__(self) -> None:
        self.calls = 0

    async def wait_for_queue(self, queue_key, timeout=None):
        self.calls += 1
        raise RuntimeError("vision provider down")


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


def _make_pipeline(parse_service) -> EventPipeline:
    pipeline = EventPipeline.__new__(EventPipeline)
    pipeline._image_parse_service = parse_service
    pipeline._logger = _RecordingLogger()
    pipeline._pending_image_willing = {}
    pipeline._image_willing_locks = {}
    pipeline._replying_queues = set()
    pipeline._post_reply_willing = {}
    pipeline._group_queue = SimpleNamespace()
    pipeline._config = None  # 走 _get_group_agent_silent_timeout_seconds 的默认值
    return pipeline


async def test_pending_queue_is_drained_when_wait_fails() -> None:
    service = _FailingParseService()
    pipeline = _make_pipeline(service)
    message = SimpleNamespace(message_id=1)
    pipeline._pending_image_willing["group:1"] = [message]

    handled: list[object] = []

    async def _fake_handle_willing(**kwargs):
        handled.append(kwargs["message"])
        return True

    pipeline._handle_willing_decision = _fake_handle_willing  # type: ignore[assignment]

    await pipeline._process_pending_image_willing("group:1")

    assert service.calls == 1
    # 消息必须被取出来并处理，而不是永久留在字典里
    assert "group:1" not in pipeline._pending_image_willing
    assert handled == [message]
    assert any("等待图片解析失败" in msg for msg, _ in pipeline._logger.warnings)


async def test_pending_queue_entry_removed_even_when_empty() -> None:
    service = _FailingParseService()
    pipeline = _make_pipeline(service)

    await pipeline._process_pending_image_willing("group:2")

    assert pipeline._pending_image_willing == {}
    assert pipeline._image_willing_locks == {}
