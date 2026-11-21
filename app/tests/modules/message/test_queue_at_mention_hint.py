"""队列 @ 提示：官方消息以 mentioned_self 为准，无可用 at 段也能标「@你的内容」。

全量消息（GROUP_MESSAGE_CREATE）可能没有 at 段、uin 未解析时 at 段 qq=0；
适配器的 mentioned_self 是权威结论，队列渲染不得再按通道名/qq=0 猜。
"""

from __future__ import annotations

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.queue import MessageQueue

BOT = 123456
OTHER = 999


def _message(
    message_id: int,
    *,
    mentioned_self: bool | None = None,
    at_qq: int | str | None = None,
    self_id: int | None = None,
    text: str = "在吗",
) -> GroupMessage:
    segments = []
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": str(at_qq)}))
    segments.append(MessageSegment(type="text", data={"text": text}))
    return GroupMessage(
        message_id=message_id,
        user_id="user_openid",
        group_id="group_openid",
        self_id=self_id,
        message=segments,
        raw_message=text,
        mentioned_self=mentioned_self,
    )


def test_official_mentioned_self_without_at_marks_queue_hint() -> None:
    """官方 @ 事件：没有可用 at 段（uin 未解析），仍要标「最新消息为@你的内容」。"""
    queue = MessageQueue()
    queue.push("g", _message(1, mentioned_self=True))

    assert "<最新消息为@你的内容，请回复这句话>" in queue.to_text("g")


def test_official_not_mentioned_does_not_mark_queue_hint() -> None:
    """全量消息未 @ 机器人（mentioned_self=False）：不标提示。"""
    queue = MessageQueue()
    queue.push("g", _message(2, mentioned_self=False, at_qq=0))

    assert "<最新消息为@你的内容" not in queue.to_text("g")


def test_official_mentioned_self_false_ignores_matching_at_segment() -> None:
    """权威结论 False 时不看 at 段，避免 uin/账号巧合造成假 @。"""
    queue = MessageQueue(bot_accounts={BOT})
    queue.push("g", _message(3, mentioned_self=False, at_qq=BOT, self_id=BOT))

    assert "<最新消息为@你的内容" not in queue.to_text("g")


def test_onebot_at_bot_still_marks_queue_hint() -> None:
    """OneBot 路径行为不变：显式 at 机器人仍标提示。"""
    queue = MessageQueue(bot_accounts={BOT})
    queue.push("g", _message(4, at_qq=BOT))

    assert "<最新消息为@你的内容，请回复这句话>" in queue.to_text("g")


def test_onebot_without_at_does_not_mark_queue_hint() -> None:
    queue = MessageQueue(bot_accounts={BOT})
    queue.push("g", _message(5))

    assert "<最新消息为@你的内容" not in queue.to_text("g")


def test_is_at_bot_segment_uses_mentioned_self_when_at_qq_unusable() -> None:
    """at 段 qq=0（uin 未解析）不参与判定，官方消息只看 mentioned_self。"""
    queue = MessageQueue(bot_accounts={BOT})
    at_segment = MessageSegment(type="at", data={"qq": "0"})

    assert queue._is_at_bot_segment(at_segment, _message(6, mentioned_self=True)) is True
    assert queue._is_at_bot_segment(at_segment, _message(7, mentioned_self=False)) is False


def test_is_at_bot_segment_onebot_at_logic_unchanged() -> None:
    """非官方消息仍按消息级 self_id / 队列 bot_accounts 匹配 at 段。"""
    queue = MessageQueue(bot_accounts={BOT})

    assert queue._is_at_bot_segment(MessageSegment(type="at", data={"qq": str(BOT)}), _message(8)) is True
    assert queue._is_at_bot_segment(MessageSegment(type="at", data={"qq": str(OTHER)}), _message(9)) is False
    assert queue._is_at_bot_segment(MessageSegment(type="text", data={"text": "hi"}), _message(10)) is False
