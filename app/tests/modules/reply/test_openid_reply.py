"""回复链路 openid 字符串化：会话主键 str，mention 支持字符串，不 int() openid。

message_id / bot_account / self_id 仍是 int；user/group/session 主键可能是官方
openid（字母数字串），一律按字符串透传。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.message import GroupMessage, MessageSegment, MessageTypeEnum
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import NullLogger

from neobot_app.bot_accounts import bind_bot_accounts
from neobot_app.config.schemas.bot import Bot, BotConfig
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.sender import ReplySender

GROUP_KEY = "openid_group_1234567890abcdef"
BOT_QQ = 10001


@pytest.fixture(autouse=True)
def _bind_accounts():
    config = BotConfig()
    config.bot = Bot(account=BOT_QQ)
    bind_bot_accounts(config, None)
    yield
    bind_bot_accounts(None, None)


def _event(*, kind: str = "group", channel: str | None = "official") -> ReplyEvent:
    event = ReplyEvent(
        mode="agent",
        conversation_ref=ConversationRef(kind=kind, id=GROUP_KEY),
        bot_account=BOT_QQ,
        neobot_channel=channel,
    )
    # 状态保持 PENDING：_build_prompt 内部会 transition(BUILDING_PROMPT)
    return event


def _openid_message() -> GroupMessage:
    return GroupMessage.model_construct(
        message_type=MessageTypeEnum.group,
        sub_type=None,
        message_id=7,
        user_id="openid_user_abcdef",
        group_id=GROUP_KEY,
        self_id=None,
        message=[MessageSegment(type="text", data={"text": "在吗"})],
        raw_message="在吗",
        sender=SimpleNamespace(card="", nickname="小明"),
        font=0,
        time=None,
        neobot_channel="official",
    )


def _orchestrator() -> ReplyOrchestrator:
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = None
    orch._prompt_store = None
    orch._bot_profile = None
    orch._willing_service = None
    orch._image_parse_service = None
    orch._debug_helper = SimpleNamespace(
        record=lambda *args, **kwargs: None,
        emit_runtime_event=AsyncMock(return_value=SimpleNamespace(consumed=False, payload={}, result=None)),
    )
    return orch


async def test_build_prompt_passes_openid_queue_key_as_string() -> None:
    orch = _orchestrator()
    builder = SimpleNamespace(build_group_chat_prompt=AsyncMock(return_value="系统提示词"))
    orch._prompt_builder = builder

    await orch._build_prompt(_event(channel="onebot"), queue=SimpleNamespace(), queue_key=GROUP_KEY)

    assert builder.build_group_chat_prompt.await_args.kwargs["group_id"] == GROUP_KEY


async def test_build_role_messages_passes_openid_queue_key_as_string() -> None:
    orch = _orchestrator()
    builder = SimpleNamespace(build_group_chat_messages=AsyncMock(return_value=[]))
    orch._prompt_builder = builder

    await orch._build_role_messages(_event(channel="onebot"), queue=SimpleNamespace(), queue_key=GROUP_KEY)

    assert builder.build_group_chat_messages.await_args.kwargs["group_id"] == GROUP_KEY


def test_agent_conversation_ids_keep_openid_user_as_string() -> None:
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    event = _event()
    event.message = _openid_message()

    conv_kind, conv_id, current_user_id = orch._agent_conversation_ids(event)

    assert conv_kind == "group"
    assert conv_id == GROUP_KEY
    assert current_user_id == "openid_user_abcdef"


def test_build_reply_segments_accepts_openid_mention() -> None:
    segments = ReplySender.build_reply_segments(
        text="在吗",
        conversation_kind="group",
        mention_user_ids=["openid_mention_1", 12345],
        channel="official",
    )

    at_segments = [segment for segment in segments if segment["type"] == "at"]
    assert [segment["data"]["qq"] for segment in at_segments] == [
        "openid_mention_1",
        "12345",
    ]


def test_self_sent_message_keeps_int_message_id_and_bot_account(tmp_path) -> None:
    """self-sent 消息：message_id/self_id/user_id 仍是 int；群 ID 按字符串透传。"""
    sender = ReplySender(
        adapter=None,
        file_server=None,
        config=None,
        bot_name="Bot",
        logger=NullLogger(),
    )

    message = sender._build_self_sent_message(
        ConversationRef(kind="group", id="123456"), "在的", -1, bot_account=BOT_QQ
    )

    assert message.message_id == -1
    assert message.user_id == BOT_QQ
    assert message.self_id == BOT_QQ
    assert str(message.group_id) == "123456"


async def test_build_prompt_does_not_blow_up_on_openid_event_message() -> None:
    """openid 事件走完整 _build_prompt：不 int(queue_key)、不读取数字假设。"""
    orch = _orchestrator()
    builder = SimpleNamespace(
        build_group_chat_prompt=AsyncMock(return_value="系统提示词"),
        build_group_chat_messages=AsyncMock(return_value=[]),
    )
    orch._prompt_builder = builder
    event = _event()
    event.message = _openid_message()

    prompt = await orch._build_prompt(event, queue=SimpleNamespace(), queue_key=GROUP_KEY, context_blocks=[])

    assert "系统提示词" in prompt
    assert builder.build_group_chat_prompt.await_args.kwargs["group_id"] == GROUP_KEY
