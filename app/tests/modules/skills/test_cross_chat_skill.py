"""CrossChatSkill 测试 — 跨聊天发送/查询/状态（依赖注入 Fake 适配器与队列）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.cross_chat_skill import CrossChatSkill


class FakeAdapter:
    """记录发送与历史查询调用的假适配器。"""

    def __init__(self, history: Any = None) -> None:
        self.group_sends: list[tuple[int, str]] = []
        self.private_sends: list[tuple[int, str]] = []
        self.group_history_calls: list[tuple[int, int]] = []
        self.friend_history_calls: list[tuple[int, int]] = []
        self._history = history

    async def send_group_msg(self, group_id: int, message: str) -> Any:
        self.group_sends.append((group_id, message))
        return SimpleNamespace(message_id=1001)

    async def send_private_msg(self, user_id: int, message: str) -> Any:
        self.private_sends.append((user_id, message))
        return SimpleNamespace(message_id=1002)

    async def get_group_msg_history(self, group_id: int, count: int) -> Any:
        self.group_history_calls.append((group_id, count))
        return self._history

    async def get_friend_msg_history(self, user_id: int, count: int) -> Any:
        self.friend_history_calls.append((user_id, count))
        return self._history


class FakeQueue:
    """记录 size/push_history/to_text 调用并返回可配置文本的消息队列。"""

    def __init__(self, text: str = "", size: int = 1) -> None:
        self._text = text
        self._size = size
        self.sizes: list[str] = []
        self.pushed: list[tuple[str, Any]] = []
        self.text_calls: list[str] = []

    def size(self, target_id: str) -> int:
        self.sizes.append(target_id)
        return self._size

    def push_history(self, target_id: str, msg: Any) -> None:
        self.pushed.append((target_id, msg))

    def to_text(self, target_id: str) -> str:
        self.text_calls.append(target_id)
        return self._text


def _parse(text: str) -> dict:
    return json.loads(text)


async def test_send_to_group_uses_group_adapter():
    """正常路径：cross_chat_send 到群应调用 send_group_msg 并返回 message_id。"""
    adapter = FakeAdapter()
    skill = CrossChatSkill(adapter=adapter)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "记得交作业",
    }))

    assert result["ok"] is True
    assert result["status"] == "sent"
    assert result["message_id"] == 1001
    assert adapter.group_sends == [(888, "记得交作业")]


async def test_send_to_private_uses_private_adapter():
    """正常路径：cross_chat_send 到私聊应调用 send_private_msg 并透传 mode。"""
    adapter = FakeAdapter()
    skill = CrossChatSkill(adapter=adapter)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "private", "target_id": "42", "task": "在吗", "mode": "wait",
    }))

    assert result["ok"] is True
    assert result["mode"] == "wait"
    assert adapter.private_sends == [(42, "在吗")]


async def test_send_missing_params_rejected():
    """异常路径：缺少 target_kind/target_id/task 任一参数时应拒绝且不调用适配器。"""
    adapter = FakeAdapter()
    skill = CrossChatSkill(adapter=adapter)

    for args in (
        {"target_kind": "group", "target_id": "888"},
        {"target_kind": "group", "task": "hi"},
        {"target_id": "888", "task": "hi"},
    ):
        result = _parse(await skill.execute("cross_chat_send", args))

        assert result["ok"] is False
        assert "缺少必要参数" in result["error"]
    assert adapter.group_sends == [] and adapter.private_sends == []


async def test_send_adapter_error_reported():
    """异常路径：适配器发送抛异常时应返回错误而非崩溃。"""
    adapter = FakeAdapter()

    async def _boom(group_id, message):
        raise RuntimeError("send failed")

    adapter.send_group_msg = _boom
    skill = CrossChatSkill(adapter=adapter)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi",
    }))

    assert result["ok"] is False
    assert "send failed" in result["error"]


async def test_send_without_adapter_rejected():
    """异常路径：adapter 未配置时应返回配置错误。"""
    skill = CrossChatSkill()

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi",
    }))

    assert result["ok"] is False
    assert "adapter 未配置" in result["error"]


async def test_query_uses_cached_queue_text():
    """正常路径：队列已有消息时应直接返回队列文本而不拉取历史。"""
    adapter = FakeAdapter()
    queue = FakeQueue(text="群888 最近在聊：天气")
    skill = CrossChatSkill(adapter=adapter, group_message_queue=queue)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "group", "target_id": "888", "query": "最近聊什么",
    }))

    assert result["ok"] is True
    assert result["history"] == "群888 最近在聊：天气"
    assert adapter.group_history_calls == []


async def test_query_fetches_history_when_queue_empty():
    """正常路径：队列为空时应拉取聊天历史并逐条写入队列后返回文本。"""
    history = SimpleNamespace(data=SimpleNamespace(messages=["m1", "m2"]))
    adapter = FakeAdapter(history=history)
    queue = FakeQueue(text="拉取后的记录", size=0)
    skill = CrossChatSkill(adapter=adapter, group_message_queue=queue)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "group", "target_id": "888", "query": "q", "message_count": 30,
    }))

    assert result["ok"] is True
    assert adapter.group_history_calls == [(888, 30)]
    assert queue.pushed == [("888", "m1"), ("888", "m2")]
    assert queue.text_calls == ["888"]


async def test_query_empty_after_fetch_returns_placeholder():
    """边界：拉取历史后仍无消息时应返回暂无消息记录的占位文本。"""
    history = SimpleNamespace(data=SimpleNamespace(messages=[]))
    adapter = FakeAdapter(history=history)
    queue = FakeQueue(text="", size=0)
    skill = CrossChatSkill(adapter=adapter, group_message_queue=queue)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "group", "target_id": "888", "query": "q",
    }))

    assert result["ok"] is True
    assert "暂无消息记录" in result["history"]


async def test_query_queue_not_configured_rejected():
    """异常路径：目标类型对应队列未配置时应返回错误。"""
    skill = CrossChatSkill(adapter=FakeAdapter(), group_message_queue=None, friend_message_queue=None)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "private", "target_id": "42", "query": "q",
    }))

    assert result["ok"] is False
    assert "消息队列未配置" in result["error"]


async def test_query_adapter_error_reported():
    """异常路径：历史拉取抛异常时应返回错误而非崩溃。"""
    adapter = FakeAdapter()

    async def _boom(group_id, count):
        raise RuntimeError("history api down")

    adapter.get_group_msg_history = _boom
    queue = FakeQueue(size=0)
    skill = CrossChatSkill(adapter=adapter, group_message_queue=queue)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "group", "target_id": "888", "query": "q",
    }))

    assert result["ok"] is False
    assert "history api down" in result["error"]


async def test_status_with_task_id_returns_unknown():
    """正常路径：带 task_id 查询状态应返回 unknown 占位说明。"""
    skill = CrossChatSkill()

    result = _parse(await skill.execute("cross_chat_status", {"task_id": "t1"}))

    assert result["ok"] is True
    assert result["task_id"] == "t1"
    assert result["status"] == "unknown"


async def test_status_without_task_id_reports_no_tasks():
    """边界：不带 task_id 时应报告无活跃任务（fire_and_forget 无队列）。"""
    skill = CrossChatSkill()

    result = _parse(await skill.execute("cross_chat_status", {}))

    assert result["ok"] is True
    assert result["active_tasks"] == 0


async def test_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = CrossChatSkill()

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown cross_chat tool" in result["error"]
