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
from neobot_app.runtime.sleep_service import DEFAULT_WAKE_PROMPT, SleepService
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
    pipeline._command_service = None
    pipeline._credential_manager = None
    pipeline._willing_service = None
    pipeline._inbound_pipeline = None
    pipeline._sleep_service = None
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
async def test_frozen_pipeline_drops_message_before_queue_and_summary():
    """运维冻结期间:消息不入队、不触发档案总结,命令系统之外的一切都不执行。"""
    from neobot_app.runtime.freeze_service import FreezeService

    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue)
    freeze_service = FreezeService()
    freeze_service.freeze(reason="token 风暴", operator="panel")
    pipeline._freeze_service = freeze_service

    recorded: list[dict] = []

    class _Summary:
        async def record_message(self, **kwargs):
            recorded.append(kwargs)

    pipeline._archive_summary_service = _Summary()

    event = {
        "post_type": "message",
        "message_type": "group",
        "message_id": 9101,
        "user_id": 7,
        "group_id": 42,
        "message": [{"type": "text", "data": {"text": "hello"}}],
        "raw_message": "hello",
    }
    await pipeline.handle_group_message_event(event)

    assert queue.size("42") == 0
    assert recorded == []


@pytest.mark.asyncio
async def test_frozen_pipeline_resumes_after_unfreeze():
    """解冻后同一条链路必须恢复正常入队。"""
    from neobot_app.runtime.freeze_service import FreezeService

    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue)
    freeze_service = FreezeService()
    pipeline._freeze_service = freeze_service

    freeze_service.freeze(reason="storm")
    pipeline._freeze_service = freeze_service
    await pipeline.handle_group_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 9102,
            "user_id": 7,
            "group_id": 42,
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "raw_message": "hello",
        }
    )
    assert queue.size("42") == 0

    freeze_service.unfreeze()
    await pipeline.handle_group_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 9103,
            "user_id": 7,
            "group_id": 42,
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "raw_message": "hello",
        }
    )
    assert queue.size("42") == 1


@pytest.mark.asyncio
async def test_private_frozen_pipeline_drops_message():
    """私聊同样受冻结熔断约束。"""
    from neobot_app.runtime.freeze_service import FreezeService

    queue = MessageQueue()
    pipeline = _pipeline_with_queue(friend_queue=queue)
    freeze_service = FreezeService()
    freeze_service.freeze(reason="storm")
    pipeline._freeze_service = freeze_service

    await pipeline.handle_private_message_event(
        {
            "post_type": "message",
            "message_type": "private",
            "message_id": 9104,
            "user_id": 7,
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "raw_message": "hello",
        }
    )

    assert queue.size("7") == 0


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
    pipeline._command_service = None
    pipeline._credential_manager = None
    pipeline._willing_service = None
    pipeline._inbound_pipeline = None
    pipeline._sleep_service = None
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
# ── 睡眠拦截 ──


def _sleep_config() -> BotConfig:
    """睡眠测试配置:私聊不预热、回复延迟 0、@唤醒延迟 0。"""
    return BotConfig(
        bot=Bot(account=0),
        chat=Chat(
            private_chat_dynamic_warmup=False,
            private_chat_reply_delay_seconds=0.0,
            at_mention_reply_delay_seconds=0.0,
        ),
    )


def _willing_fake(at_mentioned: bool = False, block_reason: str = ""):
    return SimpleNamespace(
        is_at_mentioned=lambda _m: at_mentioned,
        block_reason_for_message=lambda **_kw: block_reason,
    )


@pytest.mark.asyncio
async def test_group_message_during_sleep_only_queued():
    """睡眠中群消息只入队,不触发回复,也不唤醒 Bot。"""
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=_sleep_config())
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    pipeline._reply_orchestrator = SimpleNamespace(start_reply=lambda **kw: object())
    pipeline._willing_service = _willing_fake(at_mentioned=False)

    await pipeline.handle_group_message_event(_group_event(9501, text="hello"))

    assert queue.size("42") == 1  # 消息正常入队
    assert sleep_service.is_sleeping()  # 未被唤醒


@pytest.mark.asyncio
async def test_group_at_mention_during_sleep_wakes_and_injects_prompt():
    """睡眠中被@:唤醒 Bot,并带唤醒提示词触发回复。"""
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=_sleep_config())
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    calls: list[dict] = []

    def fake_start_reply(**kwargs):
        calls.append(kwargs)
        return object()

    pipeline._reply_orchestrator = SimpleNamespace(start_reply=fake_start_reply)
    pipeline._willing_service = _willing_fake(at_mentioned=True)

    await pipeline.handle_group_message_event(_group_event(9502, text="hi"))

    assert queue.size("42") == 1
    assert len(calls) == 1
    assert calls[0]["background_content"] == DEFAULT_WAKE_PROMPT
    assert calls[0]["decision"].manager_name == "wake_up"
    assert calls[0]["decision"].should_reply is True
    assert not sleep_service.is_sleeping()  # 被@唤醒


@pytest.mark.asyncio
async def test_sleeping_at_mention_blocked_conversation_not_woken():
    """睡眠中被@但会话被硬性屏蔽:不回复也不唤醒。"""
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=_sleep_config())
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    pipeline._reply_orchestrator = SimpleNamespace(start_reply=lambda **kw: object())
    pipeline._willing_service = _willing_fake(at_mentioned=True, block_reason="已屏蔽")

    await pipeline.handle_group_message_event(_group_event(9503, text="hi"))

    assert queue.size("42") == 1
    assert sleep_service.is_sleeping()  # 屏蔽优先,不唤醒


@pytest.mark.asyncio
async def test_private_message_during_sleep_still_replies():
    """私聊不受睡眠影响:睡眠中私聊消息依旧触发回复,睡眠状态不变。"""
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(
        group_queue=queue, friend_queue=queue, config=_sleep_config()
    )
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    pipeline._reply_orchestrator = SimpleNamespace(start_reply=lambda **kw: object())

    await pipeline.handle_private_message_event(_private_event(9504, text="hello"))

    assert queue.size("8") == 1
    assert sleep_service.is_sleeping()  # 私聊不会打断睡眠


@pytest.mark.asyncio
async def test_willing_decision_sleep_gate_returns_false_without_at():
    """睡眠中非@消息,意愿决策直接返回 False(不计算意愿)。"""
    pipeline = _pipeline_with_queue(config=_sleep_config())
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    pipeline._sleep_service = sleep_service
    evaluate = AsyncMock()
    pipeline._willing_service = SimpleNamespace(
        is_at_mentioned=lambda _m: False,
        block_reason_for_message=lambda **_kw: "",
        evaluate=evaluate,
    )

    result = await pipeline._handle_willing_decision(
        message=_group_message(9601, text="hello"),
        queue=MessageQueue(),
        queue_key="42",
    )

    assert result is False
    evaluate.assert_not_called()
    assert sleep_service.is_sleeping()



@pytest.mark.asyncio
async def test_shutdown_flush_prevents_new_fire_and_forget_tasks() -> None:
    """关闭收尾（flush_pending_summaries）之后不得再派生新的后台任务。"""
    pipeline = _pipeline_with_queue()
    pipeline._archive_summary_service = SimpleNamespace(
        record_message=AsyncMock(),
        flush_all=AsyncMock(),
    )

    await pipeline.flush_pending_summaries()
    pipeline._schedule_archive_summary(
        conversation_kind="group",
        conversation_id="42",
        message_text="ignored",
    )
    await pipeline.flush_pending_summaries()

    assert pipeline._background_tasks == set()
    pipeline._archive_summary_service.record_message.assert_not_awaited()


# ── 命令系统:入队前解析 + 回复管线拦截 + 消费标记 ──


def _command_service_mock(consumed: bool, background: str | None = None) -> AsyncMock:
    service = AsyncMock()
    service.handle_message.return_value = SimpleNamespace(
        consumed=consumed, background=background
    )
    return service


def _at_command_event(message_id: int, text: str, bot_account: int) -> dict:
    """构造一条 @bot 的命令形态群消息事件。"""
    return {
        "post_type": "message",
        "message_type": "group",
        "message_id": message_id,
        "user_id": 7,
        "group_id": 42,
        "message": [
            {"type": "at", "data": {"qq": str(bot_account)}},
            {"type": "text", "data": {"text": text}},
        ],
        "raw_message": text,
    }


@pytest.mark.asyncio
async def test_group_command_consumed_blocks_reply_and_marks_message():
    """命令被消费时:消息仍入队但打上已消费标记,且不进入意愿/回复触发。"""
    config = BotConfig(bot=Bot(account=88888))
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=config)
    pipeline._willing_service = AsyncMock()
    pipeline._command_service = _command_service_mock(consumed=True)

    await pipeline.handle_group_message_event(
        _at_command_event(9501, "/help", bot_account=88888)
    )

    assert queue.size("42") == 1
    assert queue.is_command_consumed("42", 9501)
    pipeline._command_service.handle_message.assert_awaited_once()
    pipeline._willing_service.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_group_command_consumed_with_background_starts_sync_reply():
    """sync_reply 命令:消息入队+标记后,以命令结果为背景触发回复管线。"""
    config = BotConfig(bot=Bot(account=88888))
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=config)
    # start_reply 是同步方法(返回 ReplyEvent),用普通 Mock
    from unittest.mock import Mock

    pipeline._reply_orchestrator = Mock()
    pipeline._command_service = _command_service_mock(
        consumed=True, background="<这是新的必须要回答的内容>"
    )
    pipeline._replying_queues = set()

    await pipeline.handle_group_message_event(
        _at_command_event(9502, "/sync_demo", bot_account=88888)
    )

    assert queue.size("42") == 1
    assert queue.is_command_consumed("42", 9502)
    pipeline._reply_orchestrator.start_reply.assert_called_once()
    call_kwargs = pipeline._reply_orchestrator.start_reply.call_args.kwargs
    assert call_kwargs["background_content"] == "<这是新的必须要回答的内容>"


@pytest.mark.asyncio
async def test_group_command_not_consumed_message_not_marked():
    """命令未命中(如未 @bot 或未注册)时:消息入队但不标记,继续走正常管线。"""
    from unittest.mock import Mock

    config = BotConfig(bot=Bot(account=88888))
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(group_queue=queue, config=config)
    # is_at_mentioned / evaluate 是同步方法,用普通 Mock
    willing = Mock()
    willing.is_at_mentioned.return_value = False
    willing.evaluate.return_value = SimpleNamespace(
        should_reply=False, probability=0.0, reasons=()
    )
    pipeline._willing_service = willing
    pipeline._command_service = _command_service_mock(consumed=False)

    event = _at_command_event(9503, "/help", bot_account=88888)
    # 未 @bot:命令系统返回 consumed=False
    event["message"] = [{"type": "text", "data": {"text": "/help"}}]
    await pipeline.handle_group_message_event(event)

    assert queue.size("42") == 1
    assert not queue.is_command_consumed("42", 9503)
    # 非命令消息继续走到意愿判断
    willing.evaluate.assert_called_once()


@pytest.mark.asyncio
async def test_private_command_consumed_blocks_reply_and_marks_message():
    """私聊命令被消费时:消息入队+标记,且不触发延迟回复。"""
    config = _fast_private_config()
    queue = MessageQueue()
    pipeline = _pipeline_with_queue(friend_queue=queue, config=config)
    pipeline._command_service = _command_service_mock(consumed=True)

    await pipeline.handle_private_message_event(
        {
            "post_type": "message",
            "message_type": "private",
            "message_id": 9601,
            "user_id": 8,
            "message": [{"type": "text", "data": {"text": "/help"}}],
            "raw_message": "/help",
        }
    )

    assert queue.size("8") == 1
    assert queue.is_command_consumed("8", 9601)
    pipeline._command_service.handle_message.assert_awaited_once()
