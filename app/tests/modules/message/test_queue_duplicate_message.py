"""同 key 同 message_id 入队：原地替换，不重复占位（FULL→AT 升级重投）。"""

from __future__ import annotations

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.queue import MessageQueue, QueueEntryType, SelfSentToolCall


def _message(
    message_id: int,
    text: str = "在吗",
    *,
    mentioned_self: bool | None = None,
) -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id="user_openid",
        group_id="group_openid",
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        mentioned_self=mentioned_self,
    )


def _message_entries(queue: MessageQueue, key: str) -> list:
    return [entry for entry in queue.entries(key) if entry.kind == QueueEntryType.MESSAGE]


def test_push_same_message_id_replaces_instead_of_appending() -> None:
    """FULL（未@）先入队，同 msg_id 的 AT（被@）重投后仍只有一条且内容为新消息。"""
    queue = MessageQueue()
    queue.push("g", _message(1, " /今日天气 ", mentioned_self=False))
    queue.push("g", _message(1, " /今日天气 ", mentioned_self=True))

    assert queue.size("g") == 1
    kept = queue.get("g")
    assert kept is not None
    assert kept.mentioned_self is True
    # 队列提示读取替换后的权威结论
    assert "<最新消息为@你的内容，请回复这句话>" in queue.to_text("g")
    assert queue.to_text("g").count("今日天气") == 1


def test_push_same_message_id_keeps_ordering_position() -> None:
    """替换不改变条目位置：同 id 的更新留在原位置，后面的消息仍在后面。"""
    queue = MessageQueue()
    queue.push("g", _message(1, "first"))
    queue.push("g", _message(2, "second"))

    queue.push("g", _message(1, "first-updated"))

    assert [message.message_id for message in queue.iterate_from_oldest("g")] == [1, 2]
    first = queue.get("g", 0)
    assert first is not None
    assert first.raw_message == "first-updated"
    assert len(_message_entries(queue, "g")) == 2


def test_push_same_message_id_keeps_existing_tool_call() -> None:
    """自身发言回显重投时不丢已登记的工具调用元数据。"""
    queue = MessageQueue()
    tool_call = SelfSentToolCall(name="send_reply", arguments={"text": "hi"})
    queue.push("g", _message(3, "hi"), tool_call=tool_call)
    queue.push("g", _message(3, "hi"))

    entries = _message_entries(queue, "g")
    assert len(entries) == 1
    assert entries[0].tool_call is tool_call


def test_push_different_message_ids_still_append() -> None:
    queue = MessageQueue()
    queue.push("g", _message(4, "a"))
    queue.push("g", _message(5, "b"))

    assert queue.size("g") == 2
    assert [message.message_id for message in queue.iterate_from_oldest("g")] == [4, 5]
