"""队列容量权重账本一致性测试。

入队按消息内容计算权重（合并转发 = forward_weight，默认 2），驱逐却按 kind
重算（MESSAGE 恒为 1.0），于是每来一条转发消息，账本就多出 1 点虚高权重，
队列会比配置容量更早丢弃真实消息。
"""

from __future__ import annotations

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.queue import MessageQueue, QueueEntryType


def _group_message(message_id: int, *segments: tuple[str, dict]) -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(user_id=7, nickname="tester"),
        message=[MessageSegment(type=t, data=d) for t, d in segments],
        raw_message="",
    )


def _text(message_id: int) -> GroupMessage:
    return _group_message(message_id, ("text", {"text": f"m{message_id}"}))


def _forward(message_id: int) -> GroupMessage:
    return _group_message(message_id, ("forward", {"id": "abc"}))


def _make_queue(**kwargs) -> MessageQueue:
    params = {"max_size": 6, "timestamp_interval_seconds": 0, "forward_weight": 2}
    params.update(kwargs)
    return MessageQueue(**params)


def test_forward_weight_is_accounted_symmetrically() -> None:
    queue = _make_queue()

    for message_id in (1, 2, 3):
        queue.push("k", _forward(message_id))

    # 3 条转发 = 6 权重，正好占满 max_size=6
    assert queue._weighted_counts["k"] == 6
    assert queue.size("k") == 3


def test_forward_messages_do_not_evict_early() -> None:
    """max_size=6 时应能容纳 3 条转发；旧实现会提前丢消息。"""
    queue = _make_queue()

    for message_id in (1, 2, 3):
        queue.push("k", _forward(message_id))

    assert [m.message_id for m in queue.iterate_from_oldest("k")] == [1, 2, 3]
    stats = queue.get_stats("k")
    assert stats is not None
    assert stats.dropped_messages == 0


def test_eviction_ledger_stays_consistent_after_overflow() -> None:
    """溢出驱逐后账本必须等于队列实际权重，且只丢真正放不下的那一条。"""
    queue = _make_queue()

    for message_id in (1, 2, 3, 4):
        queue.push("k", _forward(message_id))  # 第 4 条触发驱逐

    expected = sum(entry.weight for entry in queue.entries("k"))
    assert queue._weighted_counts["k"] == expected
    assert queue._weighted_counts["k"] <= 6
    # max_size=6、每条转发 2 权重 ⇒ 容量 3 条，只应丢 1 条（旧实现会丢 2 条）
    stats = queue.get_stats("k")
    assert stats is not None
    assert stats.dropped_messages == 1
    assert [m.message_id for m in queue.iterate_from_oldest("k")] == [2, 3, 4]


def test_weighted_iteration_uses_entry_weight() -> None:
    """按权重取最近消息与入队口径一致：一条转发占 2 点权重。"""
    queue = _make_queue(max_size=20)
    queue.push("k", _text(1))
    queue.push("k", _forward(2))

    newest = list(queue.iterate_entries_from_newest_weighted("k", max_weight=2))

    assert [entry.message.message_id for entry in newest] == [2]


def test_plain_messages_keep_weight_one() -> None:
    queue = _make_queue()

    queue.push("k", _text(1))
    queue.push("k", _text(2))

    assert queue._weighted_counts["k"] == 2
    assert all(
        entry.weight == 1.0
        for entry in queue.entries("k")
        if entry.kind is QueueEntryType.MESSAGE
    )
