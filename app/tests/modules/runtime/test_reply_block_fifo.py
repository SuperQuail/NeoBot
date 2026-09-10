"""ReplyBlockRegistry 的 FIFO 必须回收已消费项。

consume_message 原先只从 _keys 删除、不从 _order 删除：_order 被已消费项占满，
淘汰条件 len(_order) > max_size 实际按「事件数（含已消费）」而非「活跃阻塞数」
计算，活跃阻塞的保留窗口短于设计值。
"""

from __future__ import annotations

from neobot_app.runtime.reply_block import ReplyBlockRegistry


def _event(message_id: int, *, group_id: int = 888, message_type: str = "group") -> dict:
    return {
        "post_type": "message",
        "message_type": message_type,
        "group_id": group_id,
        "user_id": 10001,
        "message_id": message_id,
    }


def test_consume_shrinks_fifo() -> None:
    registry = ReplyBlockRegistry(max_size=10)

    registry.block_event(_event(1))
    registry.block_event(_event(2))
    assert len(registry._order) == 2

    assert registry.consume_message(_event(1)) is True

    assert len(registry._order) == 1
    assert len(registry._keys) == 1


def test_consume_by_message_id_clears_fifo_entry() -> None:
    registry = ReplyBlockRegistry(max_size=10)
    registry.block_event(_event(5))

    # 只带 message_id 的事件（无 group/user）走 _remove_message_id 分支
    assert registry.consume_message({"message_id": 5}) is True

    assert registry._order == type(registry._order)()
    assert registry._message_ids == set()


def test_consumed_items_do_not_evict_active_blocks() -> None:
    """大量「拦截后立刻消费」的消息不应挤掉仍然活跃的阻塞。"""
    registry = ReplyBlockRegistry(max_size=4)
    registry.block_event(_event(1000))

    for message_id in range(1, 50):
        registry.block_event(_event(message_id))
        registry.consume_message(_event(message_id))

    # 活跃阻塞仍在（旧实现会被已消费项挤出窗口）
    assert registry.consume_message(_event(1000)) is True


def test_fifo_still_bounded_when_never_consumed() -> None:
    registry = ReplyBlockRegistry(max_size=3)

    for message_id in range(1, 6):
        registry.block_event(_event(message_id))

    assert len(registry._order) == 3
    assert len(registry._keys) == 3
