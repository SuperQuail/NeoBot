"""ACL 信任边界：willing 名单与 reply_blacklist 只认管理员命令写入的 trusted 映射。

agent 工具写入的映射（trusted=False）只影响展示；它既不能把会话/用户放行或拦下，
也不能把管理员建立的 trusted 映射遮住。
"""

from __future__ import annotations

import pytest

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.queue import MessageQueue
from neobot_app.user_identity import (
    bind_user_identity,
    display_group_id,
    display_user_id,
    link_group_number,
    link_user_qq,
    trusted_group_number_for,
    trusted_qq_for_user,
    unlink_group_number,
)
from neobot_app.willing.service import WillingService

SYNTHETIC_USER = 9000000000002
SYNTHETIC_GROUP = 8000000000002
REAL_QQ = 123456789
REAL_GROUP = 987654321
BOT_ACCOUNT = 10001


@pytest.fixture(autouse=True)
def _bind(tmp_path):
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


def _willing(*, group_use_black_list: bool, friend_use_black_list: bool) -> WillingService:
    config = BotConfig()
    config.chat.group_use_black_list = group_use_black_list
    config.chat.group_list = [str(REAL_GROUP)]
    config.chat.friend_use_black_list = friend_use_black_list
    config.chat.friend_list = [str(REAL_QQ)]
    return WillingService(config)


def _reply_blacklisting(*qq_numbers: int) -> MessageQueue:
    return MessageQueue(bot_account=BOT_ACCOUNT, reply_blacklist=set(qq_numbers))


def _at_bot_message(user_id: int) -> GroupMessage:
    return GroupMessage(
        message_id=1,
        user_id=user_id,
        group_id=42,
        self_id=BOT_ACCOUNT,
        message=[
            MessageSegment(type="at", data={"qq": str(BOT_ACCOUNT)}),
            MessageSegment(type="text", data={"text": "在吗"}),
        ],
        raw_message="在吗",
    )


# ── willing 黑白名单 ──────────────────────────────────────


def test_untrusted_group_mapping_does_not_apply_group_blacklist() -> None:
    """agent 映射照常展示，但不能让群命中黑名单。"""
    service = _willing(group_use_black_list=True, friend_use_black_list=True)
    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP)[0]
    assert display_group_id(SYNTHETIC_GROUP) == f"群号:{REAL_GROUP}"
    assert service._is_conversation_allowed("group", str(SYNTHETIC_GROUP)) == (True, "")

    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP, trusted=True)[0]
    assert service._is_conversation_allowed("group", str(SYNTHETIC_GROUP)) == (
        False,
        "group_blacklisted",
    )


def test_untrusted_group_mapping_does_not_widen_group_whitelist() -> None:
    """白名单按真实群号配置：agent 映射不能让未列入的群通过。"""
    service = _willing(group_use_black_list=False, friend_use_black_list=True)
    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP)[0]
    assert service._is_conversation_allowed("group", str(SYNTHETIC_GROUP)) == (
        False,
        "group_not_in_whitelist",
    )

    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP, trusted=True)[0]
    assert service._is_conversation_allowed("group", str(SYNTHETIC_GROUP)) == (True, "")


def test_untrusted_user_mapping_does_not_apply_friend_lists() -> None:
    """好友黑/白名单同理：只有管理员命令写入的映射参与判定。"""
    black = _willing(group_use_black_list=True, friend_use_black_list=True)
    assert link_user_qq(SYNTHETIC_USER, REAL_QQ)[0]
    assert display_user_id(SYNTHETIC_USER) == f"QQ:{REAL_QQ}"
    assert black._is_conversation_allowed("private", str(SYNTHETIC_USER)) == (True, "")

    assert link_user_qq(SYNTHETIC_USER, REAL_QQ, trusted=True)[0]
    assert black._is_conversation_allowed("private", str(SYNTHETIC_USER)) == (
        False,
        "friend_blacklisted",
    )

    white = _willing(group_use_black_list=True, friend_use_black_list=False)
    other_user = SYNTHETIC_USER + 1
    assert link_user_qq(other_user, REAL_QQ)[0]
    assert white._is_conversation_allowed("private", str(other_user)) == (
        False,
        "friend_not_in_whitelist",
    )
    assert link_user_qq(other_user, REAL_QQ, trusted=True)[0]
    assert white._is_conversation_allowed("private", str(other_user)) == (True, "")


# ── reply_blacklist ───────────────────────────────────────


def test_untrusted_user_mapping_does_not_apply_reply_blacklist() -> None:
    """agent 映射不能把官方合成 ID 塞进或移出回复黑名单。"""
    queue = _reply_blacklisting(REAL_QQ)
    assert link_user_qq(SYNTHETIC_USER, REAL_QQ)[0]
    queue.push("42", _at_bot_message(SYNTHETIC_USER))
    assert "<最新消息为@你的内容" in queue.to_text("42")

    trusted_queue = _reply_blacklisting(REAL_QQ)
    assert link_user_qq(SYNTHETIC_USER, REAL_QQ, trusted=True)[0]
    trusted_queue.push("42", _at_bot_message(SYNTHETIC_USER))
    assert "<最新消息为@你的内容" not in trusted_queue.to_text("42")


def test_reply_blacklist_still_matches_real_qq_sender_directly() -> None:
    """OneBot 真实 QQ 号直接命中黑名单的行为不变。"""
    queue = _reply_blacklisting(REAL_QQ)
    queue.push("42", _at_bot_message(REAL_QQ))
    assert "<最新消息为@你的内容" not in queue.to_text("42")


def test_untrusted_mapping_cannot_mask_trusted_mapping() -> None:
    """trusted 查找扫全部通道 key：agent 另写一条映射不能把 ACL 用的 trusted 映射遮住。"""
    assert link_user_qq(SYNTHETIC_USER, REAL_QQ, channel="onebot", trusted=True)[0]
    assert link_user_qq(SYNTHETIC_USER, 555555555, channel="official")[0]
    assert trusted_qq_for_user(SYNTHETIC_USER) == REAL_QQ

    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP, channel="onebot", trusted=True)[0]
    assert link_group_number(SYNTHETIC_GROUP, 111222333, channel="official")[0]
    assert trusted_group_number_for(SYNTHETIC_GROUP) == REAL_GROUP


# ── trusted 映射本身不可被 agent 改写 ─────────────────────


def test_agent_cannot_tamper_trusted_group_mapping() -> None:
    """群映射与用户映射同一规则：管理员写入后 agent 既不能改也不能删。"""
    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP, trusted=True)[0]

    ok, message = link_group_number(SYNTHETIC_GROUP, 555555555)
    assert ok is False and "管理员命令" in message
    assert trusted_group_number_for(SYNTHETIC_GROUP) == REAL_GROUP

    ok, message = unlink_group_number(SYNTHETIC_GROUP)
    assert ok is False and "管理员命令" in message
    assert trusted_group_number_for(SYNTHETIC_GROUP) == REAL_GROUP
