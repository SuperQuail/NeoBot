from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.config.schemas.bot import Bot, BotConfig, Chat
from neobot_app.message.queue import MessageQueue
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.skills.image_parse_skill import ImageParseSkill


def _group_message(message_id: int, text: str = "hello") -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(user_id=7, nickname="tester"),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def _new_pipeline() -> EventPipeline:
    pipeline = object.__new__(EventPipeline)
    pipeline._recent_message_ids = deque(maxlen=200)
    pipeline._recent_message_ids_lock = asyncio.Lock()
    pipeline._background_tasks = set()
    pipeline._stopping = False
    pipeline._started = False
    pipeline._subscriptions = []
    return pipeline


@pytest.mark.asyncio
async def test_event_pipeline_dedups_duplicate_message_id():
    pipeline = _new_pipeline()
    message = _group_message(9001)

    assert not await pipeline._is_duplicate_message(message)
    assert await pipeline._is_duplicate_message(message)


@pytest.mark.asyncio
async def test_event_pipeline_dedup_skips_messages_without_message_id():
    pipeline = _new_pipeline()
    message = _group_message(9002)
    message.message_id = None

    assert not await pipeline._is_duplicate_message(message)
    assert not await pipeline._is_duplicate_message(message)


@pytest.mark.asyncio
async def test_event_pipeline_dedup_window_is_bounded():
    pipeline = object.__new__(EventPipeline)
    pipeline._recent_message_ids = deque(maxlen=2)
    pipeline._recent_message_ids_lock = asyncio.Lock()

    assert not await pipeline._is_duplicate_message(_group_message(1))
    assert not await pipeline._is_duplicate_message(_group_message(2))
    assert not await pipeline._is_duplicate_message(_group_message(3))
    assert not await pipeline._is_duplicate_message(_group_message(1))


@pytest.mark.asyncio
async def test_group_message_event_duplicate_not_pushed_twice():
    queue = MessageQueue()
    pipeline = object.__new__(EventPipeline)
    pipeline._group_queue = queue
    pipeline._friend_queue = queue
    pipeline.adapter = AsyncMock()
    pipeline._profile_service = None
    pipeline._image_parse_service = None
    pipeline._archive_summary_service = None
    pipeline._config = None
    pipeline._reply_orchestrator = None
    pipeline._reply_block_registry = None
    pipeline._willing_service = None
    pipeline._inbound_pipeline = None
    pipeline._logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
    )
    pipeline._recent_message_ids = deque(maxlen=64)
    pipeline._recent_message_ids_lock = asyncio.Lock()
    pipeline._replying_queues = set()
    pipeline._post_reply_willing = {}
    pipeline._pending_image_willing = {}
    pipeline._background_tasks = set()
    pipeline._stopping = False

    event = {
        "post_type": "message",
        "message_type": "group",
        "message_id": 9003,
        "user_id": 7,
        "group_id": 42,
        "message": [{"type": "text", "data": {"text": "hello"}}],
        "raw_message": "hello",
    }
    await pipeline.handle_group_message_event(event)
    assert queue.size("42") == 1
    await pipeline.handle_group_message_event(event)
    assert queue.size("42") == 1


@pytest.mark.asyncio
async def test_image_parse_empty_message_returns_structured_failure():
    skill = object.__new__(ImageParseSkill)

    result = await skill._extract_image_from_message(SimpleNamespace(message=[]))

    assert result[0] is None
    assert result[1]


@pytest.mark.asyncio
async def test_event_pipeline_name_resolution_uses_public_adapter():
    pipeline = object.__new__(EventPipeline)
    pipeline.adapter = AsyncMock()
    pipeline.adapter.get_stranger_info.return_value = SimpleNamespace(
        data=SimpleNamespace(nickname="Alice")
    )
    pipeline._profile_service = None
    pipeline._logger = AsyncMock()

    name = await pipeline._resolve_name(12345)

    assert name == "Alice"
    pipeline.adapter.get_stranger_info.assert_awaited_once_with(12345)


def test_legacy_adapter_request_models_import_with_package_relative_paths():
    from neobot_adapter.model.request import FriendRequest, Request

    assert Request() is not None
    assert FriendRequest(user_id=12345).user_id == 12345


# ── 以下为事件管线行为契约测试（对外可观察行为） ──


def _group_event(message_id: int | None, text: str = "hello", user_id: int = 7) -> dict:
    """构造一条群消息事件字典。"""
    return {
        "post_type": "message",
        "message_type": "group",
        "message_id": message_id,
        "user_id": user_id,
        "group_id": 42,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _private_event(message_id: int | None, text: str = "hello") -> dict:
    """构造一条私聊消息事件字典。"""
    return {
        "post_type": "message",
        "message_type": "private",
        "message_id": message_id,
        "user_id": 8,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _fast_private_config() -> BotConfig:
    """私聊处理配置：关闭动态预热并将回复延迟设为 0，避免测试长时间等待。"""
    return BotConfig(
        bot=Bot(account=0),
        chat=Chat(
            private_chat_dynamic_warmup=False, private_chat_reply_delay_seconds=0.0
        ),
    )


def _pipeline_with_queue(
    group_queue: MessageQueue | None = None,
    friend_queue: MessageQueue | None = None,
    config: BotConfig | None = None,
) -> EventPipeline:
    """构造一个仅依赖 Fake 组件的 EventPipeline（未调用真实构造函数）。

    注意：MessageQueue 定义了 __len__，空队列为 falsy，
    因此必须用显式 is None 判断而非 `or` 默认值。
    """
    pipeline = object.__new__(EventPipeline)
    pipeline._group_queue = group_queue if group_queue is not None else MessageQueue()
    pipeline._friend_queue = (
        friend_queue if friend_queue is not None else MessageQueue()
    )
    pipeline.adapter = AsyncMock()
    pipeline._profile_service = None
    pipeline._image_parse_service = None
    pipeline._archive_summary_service = None
    pipeline._config = config
    pipeline._reply_orchestrator = None
    pipeline._reply_block_registry = None
    pipeline._willing_service = None
    pipeline._inbound_pipeline = None
    pipeline._logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
    )
    pipeline._recent_message_ids = deque(maxlen=64)
    pipeline._recent_message_ids_lock = asyncio.Lock()
    pipeline._replying_queues = set()
    pipeline._post_reply_willing = {}
    pipeline._pending_image_willing = {}
    pipeline._image_willing_locks = {}
    pipeline._warmup_lock = asyncio.Lock()
    pipeline._warmed_up_friends = set()
    pipeline._background_tasks = set()
    pipeline._stopping = False
    pipeline._started = False
    pipeline._subscriptions = []
    return pipeline


@pytest.mark.asyncio
async def test_event_pipeline_dedups_duplicate_message_id_for_group_and_private():
    """群聊与私聊通道对重复 message_id 都只入队一次，且去重表跨通道共享。"""
    # Arrange
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(
        group_queue=queue,
        friend_queue=queue,
        config=_fast_private_config(),
    )
    group_event = _group_event(9101)
    private_event = _private_event(9102)

    # Act
    await pipeline.handle_group_message_event(group_event)
    await pipeline.handle_group_message_event(group_event)
    await pipeline.handle_private_message_event(private_event)
    await pipeline.handle_private_message_event(private_event)
    cross_channel = _private_event(9101)

    await pipeline.handle_private_message_event(cross_channel)

    # Assert
    assert queue.size("42") == 1
    assert queue.size("8") == 1


@pytest.mark.asyncio
async def test_event_pipeline_does_not_dedup_messages_without_message_id():
    """message_id 为 None 的消息不参与去重，重复到达仍会入队。"""
    # Arrange
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, friend_queue=queue)

    # Act
    await pipeline.handle_group_message_event(_group_event(None))
    await pipeline.handle_group_message_event(_group_event(None))

    # Assert
    assert queue.size("42") == 2


@pytest.mark.asyncio
async def test_event_pipeline_skips_reply_for_bot_own_message():
    """发送者 QQ 等于 Bot 账号时消息只入历史队列，不触发任何回复/意愿逻辑。"""
    # Arrange
    config = BotConfig(bot=Bot(account=12345))
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=config)
    pipeline._willing_service = AsyncMock()

    # Act
    await pipeline.handle_group_message_event(
        _group_event(9201, text="hi", user_id=12345)
    )

    # Assert
    assert queue.size("42") == 1
    pipeline._willing_service.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_image_willing_lock_does_not_block_different_queue_key():
    """一个 queue_key 持有分片锁期间，另一 queue_key 的锁可立即获取，互不阻塞。"""
    # Arrange
    pipeline = object.__new__(EventPipeline)
    pipeline._image_willing_locks = {}
    started_a = asyncio.Event()
    release_a = asyncio.Event()

    async def hold_a() -> None:
        async with pipeline._image_willing_lock("a"):
            started_a.set()
            await release_a.wait()

    task_a = asyncio.create_task(hold_a())
    await started_a.wait()

    # Act: "a" 持锁期间获取 "b" 的锁（若串行化将在此阻塞）
    async with pipeline._image_willing_lock("b"):
        pass

    # Assert
    release_a.set()
    await task_a


@pytest.mark.asyncio
async def test_private_warmup_failure_does_not_mark_user_warmed():
    """私聊历史预热失败后该用户不应被标记为已预热，以便后续消息重试预热。"""
    # Arrange
    config = BotConfig(
        bot=Bot(account=0),
        chat=Chat(private_chat_dynamic_warmup=True),
    )
    pipeline = _pipeline_with_queue(config=config)
    pipeline.adapter = AsyncMock()
    pipeline.adapter.get_friend_msg_history.side_effect = RuntimeError(
        "history unavailable"
    )

    # Act
    await pipeline._maybe_warmup_friend_chat("123")

    # Assert
    assert "123" not in pipeline._warmed_up_friends


@pytest.mark.asyncio
async def test_events_enqueue_in_receive_order():
    """按到达顺序连续处理的事件应以相同顺序进入队列。"""
    # Arrange
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, friend_queue=queue)

    # Act
    await pipeline.handle_group_message_event(_group_event(9301, text="first"))
    await pipeline.handle_group_message_event(_group_event(9302, text="second"))

    # Assert
    first = queue.get("42", 0)
    second = queue.get("42", 1)
    assert first.message_id == 9301
    assert second.message_id == 9302


@pytest.mark.asyncio
async def test_flush_cancels_and_awaits_tracked_background_tasks() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class _ArchiveSummary:
        def __init__(self) -> None:
            self.flush_all = AsyncMock()

        async def record_message(self, **kwargs) -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    pipeline = _pipeline_with_queue()
    archive = _ArchiveSummary()
    pipeline._archive_summary_service = archive

    pipeline._schedule_archive_summary(
        conversation_kind="group",
        conversation_id="42",
        message_text="pending",
    )
    await started.wait()
    task = next(iter(pipeline._background_tasks))

    await pipeline.flush_pending_summaries()

    assert task.cancelled()
    assert cancelled.is_set()
    assert pipeline._background_tasks == set()
    archive.flush_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_prevents_new_fire_and_forget_tasks() -> None:
    pipeline = _pipeline_with_queue()
    pipeline._archive_summary_service = SimpleNamespace(
        record_message=AsyncMock(),
        flush_all=AsyncMock(),
    )

    pipeline.stop()
    pipeline._schedule_archive_summary(
        conversation_kind="group",
        conversation_id="42",
        message_text="ignored",
    )
    await pipeline.flush_pending_summaries()

    assert pipeline._background_tasks == set()
    pipeline._archive_summary_service.record_message.assert_not_awaited()
