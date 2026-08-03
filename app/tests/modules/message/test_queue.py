"""MessageQueue 测试：加权计数、容量上限、迭代顺序、并发、ReactionEntry 与 __len__ 语义。"""

from __future__ import annotations

import asyncio

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.queue import MessageQueue, QueueEntryType, ReactionEntry


def _group_message(message_id: int, *segments: tuple[str, dict]) -> GroupMessage:
    """构造带指定消息段的群消息。"""
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(user_id=7, nickname="tester"),
        message=[MessageSegment(type=t, data=d) for t, d in segments],
        raw_message="",
    )


def test_compute_message_weight_counts_forward_as_double() -> None:
    """Arrange: 构造普通文本消息与 forward 段消息；Act: 计算各自权重；Assert: forward 为 2、普通为 1。"""
    queue = MessageQueue()
    normal = _group_message(1, ("text", {"text": "hi"}))
    forward = _group_message(2, ("forward", {"id": "abc"}))
    raw_forward = _group_message(3)

    assert queue._compute_message_weight(normal) == 1.0
    assert queue._compute_message_weight(forward) == 2.0
    raw_forward.raw_message = "[CQ:forward,id=abc]"
    assert queue._compute_message_weight(raw_forward) == 2.0


def test_push_drops_oldest_message_when_weighted_capacity_exceeded() -> None:
    """Arrange: max_size=3 队列；Act: 依次 push 4 条普通消息；Assert: 仅保留最新 3 条且 oldest 已被丢弃计数。"""
    queue = MessageQueue(max_size=3)
    for i in range(1, 5):
        queue.push("g", _group_message(i, ("text", {"text": f"m{i}"})))

    assert queue.size("g") == 3
    assert [m.message_id for m in queue.iterate_from_oldest("g")] == [2, 3, 4]
    stats = queue.get_stats("g")
    assert stats is not None
    assert stats.dropped_messages == 1
    assert stats.oldest_message_id == 2
    assert stats.newest_message_id == 4


def test_poke_entries_use_low_weight_and_never_trigger_drop() -> None:
    """Arrange: max_size=2、poke_weight=0.2 的队列；Act: push 10 条 poke；Assert: 消息数 10、加权计数 2.0、无丢弃。"""
    from neobot_app.message.queue import PokeEntry

    queue = MessageQueue(max_size=2, poke_weight=0.2)
    for i in range(10):
        queue.push_poke(
            "g",
            PokeEntry(sender_id=i, user_id=i, target_id=99, sub_type="poke"),
            occurred_at=1000 + i,
        )

    assert queue.size("g") == 10
    assert queue._weighted_counts["g"] == pytest.approx(2.0)
    assert queue.get_stats("g").dropped_messages == 0


@pytest.mark.xfail(
    reason=(
        "BUG-QUEUE-001 容量上限在单次丢弃不足以恢复时失效：max_size=1 时 forward 消息（权重 2）"
        "使 _weighted_counts 恒超过 max_size（空队列 append 不丢弃、每次 push 只丢一条）"
    ),
    strict=False,
)
def test_weighted_count_never_exceeds_max_size_even_for_oversized_entry() -> None:
    """Arrange: max_size=1 的队列；Act: push 权重为 2 的 forward 消息；Assert: 加权计数必须不超过容量上限。"""
    queue = MessageQueue(max_size=1)
    queue.push("g", _group_message(1, ("forward", {"id": "abc"})))

    assert queue._weighted_counts["g"] <= queue.max_size


def test_iterate_entries_from_newest_weighted_skips_timestamp_and_cuts_by_weight() -> None:
    """Arrange: 3 条带时间戳间隔的消息（出现 TIMESTAMP 条目）；Act: 按 max_weight=1.5 从新到旧迭代；Assert: 跳过时间戳且超出权重即停止。"""
    queue = MessageQueue(timestamp_interval_seconds=300)
    queue.push_history("g", _group_message(1, ("text", {"text": "a"})), occurred_at=100)
    queue.push_history("g", _group_message(2, ("text", {"text": "b"})), occurred_at=401)
    queue.push_history("g", _group_message(3, ("text", {"text": "c"})), occurred_at=702)

    entries = list(queue.iterate_entries_from_newest_weighted("g", max_weight=1.5))
    assert [e.kind for e in entries] == [QueueEntryType.MESSAGE]
    assert [e.message.message_id for e in entries] == [3]
    assert any(e.kind == QueueEntryType.TIMESTAMP for e in queue.entries("g"))


def test_iterate_order_and_missing_key_behavior() -> None:
    """Arrange: 同一 key 的 3 条消息；Act: 正反两个方向迭代及对缺失 key 迭代；Assert: 顺序正确且缺失 key 抛 KeyError。"""
    queue = MessageQueue()
    for i in range(1, 4):
        queue.push("g", _group_message(i, ("text", {"text": str(i)})))

    assert [m.message_id for m in queue.iterate_from_oldest("g")] == [1, 2, 3]
    assert [m.message_id for m in queue.iterate_from_newest("g")] == [3, 2, 1]
    assert list(queue.iterate_entries_from_newest_weighted("missing", 10.0)) == []
    with pytest.raises(KeyError):
        list(queue.iterate_from_oldest("missing"))


def test_push_reaction_target_missing_is_noop_and_found_appends_entry() -> None:
    """Arrange: 队列已含消息 1001；Act: 对不存在的目标与存在的目标分别 push_reaction；Assert: 前者无副作用、后者新增 REACTION 条目并计入加权。"""
    queue = MessageQueue(reaction_weight=0.2)
    queue.push("g", _group_message(1001, ("text", {"text": "target"})))

    queue.push_reaction(
        "g",
        ReactionEntry(
            target_message_id=9999,
            emoji_id=14,
            operator_user_id=777,
            operator_name="ali",
        ),
    )
    assert queue.size("g") == 1

    queue.push_reaction(
        "g",
        ReactionEntry(
            target_message_id=1001,
            emoji_id=14,
            operator_user_id=777,
            operator_name="ali",
        ),
    )
    assert queue.size("g") == 2
    entries = queue.entries("g")
    assert entries[-1].kind == QueueEntryType.REACTION
    assert entries[-1].reaction.emoji_id == 14
    assert queue._weighted_counts["g"] == pytest.approx(1.2)
    assert queue.get_recent_sender_ids("g", max_weight=1.5) == [777, 7]


def test_len_semantics_count_messages_across_all_keys() -> None:
    """Arrange: 两个 key 分别 push 2/1 条消息；Act: 读取 len/size/成员判断与 __getitem__；Assert: len 等于跨 key 总消息数。"""
    queue = MessageQueue()
    queue.push("a", _group_message(1, ("text", {"text": "x"})))
    queue.push("a", _group_message(2, ("text", {"text": "y"})))
    queue.push("b", _group_message(3, ("text", {"text": "z"})))

    assert len(queue) == 3
    assert queue.size() == 3
    assert queue.size("a") == 2
    assert queue.size("b") == 1
    assert "a" in queue
    assert "missing" not in queue
    assert [m.message_id for m in queue["a"]] == [1, 2]

    queue.clear("a")
    assert len(queue) == 1
    assert "a" not in queue
    with pytest.raises(KeyError):
        queue["a"]


def test_timestamp_inserted_only_when_gap_exceeds_interval() -> None:
    """Arrange: 间隔 300s 的队列；Act: 按 100/200/501s push 三条历史消息；Assert: 只有跨过间隔的那条前面出现 TIMESTAMP。"""
    queue = MessageQueue(timestamp_interval_seconds=300)
    queue.push_history("g", _group_message(1, ("text", {"text": "a"})), occurred_at=100)
    queue.push_history("g", _group_message(2, ("text", {"text": "b"})), occurred_at=200)
    queue.push_history("g", _group_message(3, ("text", {"text": "c"})), occurred_at=501)

    kinds = [e.kind for e in queue.entries("g")]
    assert kinds == [
        QueueEntryType.MESSAGE,
        QueueEntryType.MESSAGE,
        QueueEntryType.TIMESTAMP,
        QueueEntryType.MESSAGE,
    ]


def test_constructor_rejects_invalid_parameters() -> None:
    """Arrange: 非法参数组合；Act: 构造 MessageQueue；Assert: 各参数分别抛出 ValueError。"""
    with pytest.raises(ValueError):
        MessageQueue(max_size=0)
    with pytest.raises(ValueError):
        MessageQueue(timestamp_interval_seconds=-1)
    with pytest.raises(ValueError):
        MessageQueue(cq_fallback_max_length=0)


async def test_concurrent_push_and_read_from_multiple_tasks() -> None:
    """Arrange: 预置 key 的队列与 40 条待并发消息；Act: 用 asyncio.gather + to_thread 并发 push 与并发读取；Assert: 全部消息可达、读取无丢失无异常。"""
    queue = MessageQueue(max_size=100)
    queue.push("g", _group_message(0, ("text", {"text": "seed"})))
    ids = list(range(2000, 2040))

    def push_one(message_id: int) -> None:
        queue.push("g", _group_message(message_id, ("text", {"text": str(message_id)})))

    def read_one(message_id: int):
        return queue.find_by_message_id("g", message_id) is not None

    await asyncio.gather(*(asyncio.to_thread(push_one, i) for i in ids))
    results = await asyncio.gather(*(asyncio.to_thread(read_one, i) for i in ids))

    assert all(results)
    assert queue.find_by_message_id("g", 0) is not None
    assert queue.get_last_message_id("g") in ids
