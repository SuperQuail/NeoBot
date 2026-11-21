"""fix(14):聊天记录每条 user 消息带确定性年龄（相对快照最新消息，不读墙钟）。"""

from __future__ import annotations

import json
import time

import pytest
from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment

import neobot_app.time_context as time_context
from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.role_messages import (
    build_role_messages,
    build_role_messages_from_entries,
    _format_message_age,
)

KEY = "888888"
BASE = 1_700_000_000


def _message(message_id: int, text: str = "消息", *, user_id: int = 10001, nickname: str = "群友"):
    return GroupMessage(
        message_id=message_id,
        user_id=user_id,
        group_id=int(KEY),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=PostMessageMessagesender(user_id=user_id, nickname=nickname),
    )


def _queue(messages: list[tuple[int, GroupMessage]], *, bot_account: int = 0) -> MessageQueue:
    """按 (occurred_at, message) 顺序入队；固定时间戳间隔，避免额外的 TS 行。"""
    queue = MessageQueue(timestamp_interval_seconds=10**9, bot_account=bot_account)
    for occurred_at, message in messages:
        queue.push(KEY, message, occurred_at=occurred_at)
    return queue


def _user_lines(messages: list[dict[str, str]]) -> list[str]:
    return [m["content"] for m in messages if m["role"] == "user" and "[msg_id=" in m["content"]]


def test_ages_are_relative_to_latest_message_in_snapshot():
    queue = _queue([(BASE, _message(1, "旧问题")), (BASE + 14 * 60, _message(2, "新消息"))])

    lines = _user_lines(build_role_messages(queue, KEY))

    assert "[14分钟前]" in lines[0]
    assert "[刚刚]" in lines[1]


def test_render_is_independent_of_wall_clock(monkeypatch):
    """A1 缓存安全护栏：同一队列快照 + 两个相差数小时的假时钟 -> 逐字节一致。"""
    queue = _queue([(BASE, _message(1)), (BASE + 300, _message(2))])

    monkeypatch.setattr(time, "time", lambda: 0)
    monkeypatch.setattr(time_context, "epoch_seconds_int", lambda: 0)
    first = build_role_messages(queue, KEY)

    monkeypatch.setattr(time, "time", lambda: 4_102_444_800)
    monkeypatch.setattr(time_context, "epoch_seconds_int", lambda: 4_102_444_800)
    second = build_role_messages(queue, KEY)

    assert first == second


def test_all_new_without_last_reply_still_carries_ages():
    queue = _queue([(BASE, _message(1)), (BASE + 3600, _message(2))])

    lines = _user_lines(build_role_messages(queue, KEY, all_new=True))

    assert "[1小时前]" in lines[0]
    assert "[刚刚]" in lines[1]


def test_assistant_lines_stay_free_of_any_annotation():
    bot = _message(2, "我回复过了", user_id=999, nickname="Bot")
    queue = _queue([(BASE, _message(1, "问题")), (BASE + 60, bot)], bot_account=999)

    messages = build_role_messages(queue, KEY, bot_account=999)
    assistant = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == ""
    call = assistant[0]["tool_calls"][0]
    assert call["function"]["name"] == "send_reply"
    arguments = json.loads(call["function"]["arguments"])
    assert arguments["text"] == "我回复过了"
    assert "分钟前" not in arguments["text"] and "[msg_id=" not in arguments["text"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == call["id"] for m in messages)


def test_quoted_message_carries_its_own_age():
    quoted = _message(1, "旧引用", nickname="用户甲")
    quoted.time = BASE
    main = _message(2, "新回复", nickname="用户乙")
    main.message = [
        MessageSegment(type="reply", data={"id": "1"}),
        MessageSegment(type="text", data={"text": "新回复"}),
    ]
    queue = _queue([(BASE, quoted), (BASE + 600, main)])
    queue.entries(KEY)[-1].replied_messages = [quoted]

    lines = _user_lines(build_role_messages(queue, KEY))

    assert any("[被回复消息]" in line and "[10分钟前]" in line for line in lines)


def test_incremental_build_uses_full_context_reference_point():
    queue = _queue([(BASE, _message(1)), (BASE + 900, _message(2))])
    entries = queue.entries(KEY)

    lines = _user_lines(build_role_messages_from_entries(entries[-1:], queue, KEY))

    assert lines and "[刚刚]" in lines[0]


@pytest.mark.parametrize(
    "occurred_at,expected",
    [
        (None, ""),
        (BASE, "刚刚"),
        (BASE - 59, "刚刚"),
        (BASE - 60, "1分钟前"),
        (BASE - 3599, "59分钟前"),
        (BASE - 3600, "1小时前"),
        (BASE - 86399, "23小时前"),
        (BASE - 86400, "1天前"),
        (BASE + 100, "刚刚"),  # 未来时间（时钟回拨）按刚刚处理，不出现负数
    ],
)
def test_format_message_age_boundaries(occurred_at, expected):
    assert _format_message_age(occurred_at, BASE) == expected
