"""消息队列的工具调用条目：低权重入队、随聊天记录裁剪、compact 文本渲染。"""

from __future__ import annotations

from neobot_app.message.queue import MessageQueue, QueueEntryType, SelfSentToolCall
from neobot_app.reply._utils import entry_fingerprint

KEY = "42"
SECRET = "内部机密查询内容"


def _record(*, ok: bool = True, call_id: str = "call_1", name: str = "web_search") -> SelfSentToolCall:
    return SelfSentToolCall(
        name=name,
        arguments={"query": SECRET},
        result={"ok": ok, "value": "机密结果"},
        ok=ok,
        compact=True,
        call_id=call_id,
    )


def _tool_entries(queue: MessageQueue) -> list:
    return [entry for entry in queue.entries(KEY) if entry.kind == QueueEntryType.TOOL_CALL]


def test_push_tool_call_appends_low_weight_entry() -> None:
    queue = MessageQueue(bot_account=10001)

    queue.push_tool_call(KEY, _record())

    entries = _tool_entries(queue)
    assert len(entries) == 1
    assert entries[0].tool_call.name == "web_search"
    assert entries[0].weight == queue.self_sent_weight
    # 低权重：比其他事件（1.0）更不容易挤占聊天记录的观测窗口
    assert entries[0].weight < 1.0
    assert queue.size(KEY) == 1


def test_clone_keeps_tool_call_records() -> None:
    queue = MessageQueue(bot_account=10001)
    queue.push_tool_call(KEY, _record(call_id="call_clone"))

    cloned = queue.clone(KEY)

    entries = [entry for entry in cloned.entries(KEY) if entry.kind == QueueEntryType.TOOL_CALL]
    assert entries[0].tool_call.call_id == "call_clone"
    assert entries[0].tool_call.arguments == {"query": SECRET}


def test_tool_call_entries_are_trimmed_with_chat_records() -> None:
    """容量裁剪按权重逐条丢；工具调用与其前后聊天记录一起被裁，不留孤儿。"""
    queue = MessageQueue(max_size=3, bot_account=10001)
    from neobot_adapter.model.message import GroupMessage, MessageSegment

    def _user(index: int):
        return GroupMessage(
            message_id=index,
            user_id=1000 + index,
            group_id=int(KEY),
            message=[MessageSegment(type="text", data={"text": f"消息{index}"})],
            raw_message=f"消息{index}",
        )

    for index in range(5):
        queue.push(KEY, _user(index))
        queue.push_tool_call(KEY, _record(call_id=f"call_{index}"))

    retained = _tool_entries(queue)
    assert 0 < len(retained) < 5
    # 保留的工具条目与队列里的消息按入队顺序交错，没有悬空引用
    assert [entry.tool_call.call_id for entry in retained] == [f"call_{index}" for index in range(5 - len(retained), 5)]


def test_to_text_renders_tool_call_compactly() -> None:
    queue = MessageQueue(bot_account=10001)
    queue.push_tool_call(KEY, _record())
    queue.push_tool_call(KEY, _record(ok=False, call_id="call_2", name="read_file"))

    text = queue.to_text(KEY)

    assert "[工具调用] web_search 成功" in text
    assert "[工具调用] read_file 失败" in text
    # 参数/结果内容不进聊天管线
    assert SECRET not in text
    assert "机密结果" not in text


def test_entry_fingerprint_distinguishes_tool_calls() -> None:
    """指纹按 call_id 区分：同一管线里多次同名工具调用不会被去重成一条。"""
    queue = MessageQueue(bot_account=10001)
    queue.push_tool_call(KEY, _record(call_id="call_a"))
    queue.push_tool_call(KEY, _record(call_id="call_b"))

    fingerprints = [entry_fingerprint(entry) for entry in _tool_entries(queue)]

    assert len(set(fingerprints)) == 2
    assert fingerprints[0].startswith("tool_call:call_a")


def test_tool_call_does_not_become_oldest_message_id() -> None:
    """工具调用没有 message_id：不能污染 oldest/newest 消息统计与 last_reply 定位。"""
    queue = MessageQueue(bot_account=10001)
    queue.push_tool_call(KEY, _record())

    stats = queue.get_stats(KEY)
    assert stats is not None
    assert stats.oldest_message_id is None
    assert stats.newest_message_id is None
    assert queue.get_last_message_id(KEY) is None
