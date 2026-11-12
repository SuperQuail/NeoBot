"""openid 提示词展示：group/user 会话主键是字符串，显示完整 openid（不截断、不标 ID）。

官方通道只给 openid；提示词里未映射的 openid 应原样显示为 openid:<完整值>，
人工绑定过的显示真实 QQ 号。任何地方都不能 int() 或按位数截断 openid。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_adapter.model.message import GroupMessage, MessageSegment, MessageTypeEnum

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.user_identity import bind_user_identity

GROUP_ID = "openid_group_1234567890abcdef"
USER_ID = "openid_user_abcdef1234567890"


class _ProfileService:
    def __init__(self) -> None:
        self.group_ids: list[object] = []

    async def get_group_name(self, group_id):
        self.group_ids.append(group_id)
        return "测试群"

    async def render_group_member_list(
        self, group_id, message_queue, *, archive_fetch_window=None, include_archives=False
    ):
        self.group_ids.append(group_id)
        return ""

    async def render_bot_group_admin_status(self, group_id, bot_account, message_queue):
        self.group_ids.append(group_id)
        return ""

    async def render_group_owner_text(self, group_id, message_queue):
        self.group_ids.append(group_id)
        return ""

    async def ensure_user_profile(self, user_id):
        return SimpleNamespace(nick_name="小明", remark="", profile="")

    async def render_friend_info(self, user_id, *, profile=None):
        return ""


class _EmptyQueue:
    def to_text(self, key, last_reply_message_id=None, *, all_new=False):
        return ""

    def iterate_from_newest(self, key):
        raise KeyError(key)


@pytest.fixture(autouse=True)
def _identity_map(tmp_path):
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


def _builder() -> PromptBuilder:
    return PromptBuilder(BotConfig(), _ProfileService())


def _openid_message() -> GroupMessage:
    return GroupMessage.model_construct(
        message_type=MessageTypeEnum.group,
        sub_type=None,
        message_id=1,
        user_id=USER_ID,
        group_id=GROUP_ID,
        self_id=None,
        message=[MessageSegment(type="text", data={"text": "在吗"})],
        raw_message="在吗",
        sender=SimpleNamespace(card="", nickname="小明"),
        font=0,
        time=None,
        neobot_channel="official",
    )


async def test_group_prompt_accepts_openid_group_id() -> None:
    profile = _ProfileService()
    builder = PromptBuilder(BotConfig(), profile)

    prompt = await builder.build_group_chat_prompt(GROUP_ID, _EmptyQueue())

    assert GROUP_ID in prompt
    # 下游资料服务吃字符串，不能是 int() 失败的空值
    assert profile.group_ids and all(item == GROUP_ID for item in profile.group_ids)


async def test_friend_prompt_accepts_openid_user_id() -> None:
    builder = _builder()

    prompt = await builder.build_friend_chat_prompt(USER_ID, _EmptyQueue())

    assert prompt


async def test_chat_context_shows_full_openid_ids() -> None:
    event = ReplyEvent(neobot_channel="official")
    event.message = _openid_message()

    context = ReplyOrchestrator._build_chat_context(event, GROUP_ID)

    assert context is not None
    # 身份标签使用全角冒号（openid：<完整值>），断言只看完整值不截断
    assert USER_ID in context
    assert GROUP_ID in context
    assert "openid" in context
    assert f"ID:{USER_ID}" not in context


def test_is_official_platform_uses_event_channel_not_id_shape() -> None:
    """通道判定只看事件 neobot_channel，不看 ID 是不是数字（openid 不是数字）。"""
    from neobot_app.reply.orchestrator_parts.prompt_build import PromptBuildMixin

    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orchestrator._bot_profile = None

    assert PromptBuildMixin._is_official_platform(orchestrator, ReplyEvent(neobot_channel="official")) is True
    assert PromptBuildMixin._is_official_platform(orchestrator, ReplyEvent(neobot_channel="onebot")) is False


async def test_builder_role_messages_accept_openid_ids() -> None:
    """builder 的聊天记录构建接受 openid 字符串主键（message_id 仍是 int）。"""
    from neobot_app.message.queue import MessageQueue

    builder = _builder()

    messages = await builder.build_group_chat_messages(GROUP_ID, MessageQueue())

    assert messages == []
