"""openid 字符串身份：队列/编号/角色消息一律按字符串主键，不做 int()/位数判断。

官方通道只给 openid（字母数字串），OneBot 给真实 QQ 数字；两者都可能是
user/group/session 主键。message_id、bot_account、self_id 仍是 int。
"""

from __future__ import annotations

from neobot_adapter.model.message import GroupMessage, MessageSegment, MessageTypeEnum

from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue, QueueEntryType, SelfSentToolCall
from neobot_app.message.queue_parts.common import PokeEntry, ReactionEntry
from neobot_app.prompt.role_messages import build_role_messages

KEY = "openid_group_xyz"
OPENID_USER = "openid_user_1234567890abcdef"
BOT_QQ = 10001


def _openid_group_message(
    *,
    user_id: object = OPENID_USER,
    group_id: object = KEY,
    text: str = "你好",
    sender=None,
    segments=None,
) -> GroupMessage:
    return GroupMessage.model_construct(
        message_type=MessageTypeEnum.group,
        sub_type=None,
        message_id=101,
        user_id=user_id,
        group_id=group_id,
        self_id=None,
        message=segments or [MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=sender,
        font=0,
        time=None,
        neobot_channel="official",
    )


def test_openid_user_and_group_ids_stay_strings() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)

    queue.push(KEY, _openid_group_message())

    entry = next(item for item in queue.entries(KEY) if item.kind == QueueEntryType.MESSAGE)
    assert entry.message.group_id == KEY
    assert entry.message.user_id == OPENID_USER
    # 机器人账号仍是 int，不受 openid 化影响
    assert queue.bot_accounts == {BOT_QQ}


def test_is_bot_message_tolerates_string_ids() -> None:
    from neobot_app.message.queue import is_bot_message

    openid_message = _openid_group_message()
    assert is_bot_message(openid_message, {BOT_QQ}) is False

    numeric_string_message = _openid_group_message(user_id=str(BOT_QQ))
    assert is_bot_message(numeric_string_message, {BOT_QQ}) is True

    self_echo = _openid_group_message(user_id=OPENID_USER)
    self_echo.self_id = None
    assert is_bot_message(self_echo, set()) is False


def test_queue_text_shows_full_openid_sender() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(KEY, _openid_group_message(text="在吗"))

    text = queue.to_text(KEY)

    # 提示词/历史里展示完整 openid，而不是截断的 ID 或错误的 QQ 前缀
    assert f"openid:{OPENID_USER}" in text
    assert OPENID_USER in text
    assert "在吗" in text


def test_numbering_renders_full_openid_sender() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(KEY, _openid_group_message(text="在吗"))
    numbering = MessageNumbering(bot_account=BOT_QQ)

    text = numbering.apply(queue, KEY)

    assert f"openid:{OPENID_USER}" in text
    assert OPENID_USER in text


def test_at_segment_renders_openid_mention() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    message = _openid_group_message(
        segments=[
            MessageSegment(type="at", data={"qq": "openid_mention_1", "name": "小明"}),
            MessageSegment(type="text", data={"text": " 在吗"}),
        ]
    )
    queue.push(KEY, message)

    text = queue.to_text(KEY)

    assert "@小明(openid:openid_mention_1)" in text


def test_reaction_and_poke_openid_ids_render_without_int() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(KEY, _openid_group_message())
    queue.push_reaction(
        KEY,
        ReactionEntry(
            target_message_id=101,
            emoji_id=1,
            operator_user_id="openid_operator_9",
            operator_name="小红",
        ),
    )
    queue.push_poke(
        KEY,
        PokeEntry(
            sender_id="openid_sender_1",
            user_id="openid_sender_1",
            target_id="openid_target_2",
            sub_type="poke",
            sender_name="小明",
            target_name="小红",
        ),
    )

    text = queue.to_text(KEY)

    assert "小红" in text
    assert "小明" in text


def test_role_messages_keep_openid_user_as_user() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(KEY, _openid_group_message(text="在吗"))

    messages = build_role_messages(queue, KEY, bot_account=BOT_QQ)

    user_texts = [
        message["content"]
        for message in messages
        if message.get("role") == "user" and "在吗" in str(message.get("content") or "")
    ]
    assert user_texts
    assert "openid:" in user_texts[0]


def test_tool_call_entries_still_pair_with_openid_session() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(KEY, _openid_group_message(text="搜一下"))
    queue.push_tool_call(
        KEY,
        SelfSentToolCall(
            name="web_search",
            arguments={"query": "x"},
            result={"ok": True},
            ok=True,
            compact=True,
            call_id="call_1",
        ),
    )

    messages = build_role_messages(queue, KEY, bot_account=BOT_QQ)
    call_ids = [message["tool_calls"][0]["id"] for message in messages if message.get("tool_calls")]
    tool_ids = [message["tool_call_id"] for message in messages if message.get("role") == "tool"]

    assert call_ids == tool_ids == ["call_1"]
    assert any(entry.kind == QueueEntryType.TOOL_CALL for entry in queue.entries(KEY))
