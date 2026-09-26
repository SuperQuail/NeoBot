"""CrossChatSkill 测试 — 跨聊天投递/回传/查询/状态。

关键约定（旧测试把错误行为写成了规格，已重写）：
    cross_chat_send 的 task 是**交给目标聊天主 agent 的任务**，不是要发到那个
    聊天的消息。因此任何情况下都不允许调用 adapter.send_group_msg/send_private_msg
    把 task 原文贴进目标聊天。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.cross_chat_skill import CrossChatSkill, extract_leading_markers


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


class FakeEvent:
    """假 ReplyEvent：回复正文 + 是否已终结。"""

    def __init__(self, reply: str = "", *, terminal: bool = True, error: str = "") -> None:
        self.generated_text = reply
        self.error = error
        self.is_terminal = terminal


class FakeOrchestrator:
    """记录 start_background_reply 调用；返回预设事件（None 表示目标管线正忙）。"""

    def __init__(self, event: Any = None, *, boom: bool = False) -> None:
        self.calls: list[dict] = []
        self._event = event
        self._boom = boom

    def start_background_reply(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._boom:
            raise RuntimeError("pipeline refused")
        return self._event


class FakeHub:
    """记录 publish 调用（投递与回传共用）。"""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, **kwargs: Any) -> bool:
        self.published.append(kwargs)
        return True


def _parse(text: str) -> dict:
    return json.loads(text)


async def _drain_watchers(skill: CrossChatSkill) -> None:
    """等后台回传任务跑完（fire_and_forget + response 才会派生）。"""
    for _ in range(100):
        if skill._watchers:
            await asyncio.gather(*list(skill._watchers), return_exceptions=True)
            return
        await asyncio.sleep(0.01)
    raise AssertionError("没有派生后台回传任务")


# ── 投递：绝不把 task 当消息发进目标聊天 ────────────────────────────────────


async def test_send_delivers_to_target_agent_and_never_posts_to_chat():
    """核心回归：task 交给目标聊天主 agent，绝不经 adapter 贴进目标群。"""
    adapter = FakeAdapter()
    orchestrator = FakeOrchestrator(FakeEvent())
    skill = CrossChatSkill(adapter=adapter, orchestrator=orchestrator)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "告知群里明天十点集合",
                    "pipeline_key": "group:111",
    }))

    assert result["ok"] is True
    assert result["status"] == "delivered"
    assert result["target"] == "group:888"
    assert orchestrator.calls == [{
        "kind": "group", "conversation_id": "888", "content": "告知群里明天十点集合",
        "manager_name": "cross_chat", "reasons": ["跨聊天任务"],
    }]
    # 这条断言就是旧 bug 的护栏
    assert adapter.group_sends == [] and adapter.private_sends == []


async def test_send_to_private_passes_through_kind():
    adapter = FakeAdapter()
    orchestrator = FakeOrchestrator(FakeEvent())
    skill = CrossChatSkill(adapter=adapter, orchestrator=orchestrator)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "private", "target_id": "42", "task": "在吗",
    }))

    assert result["ok"] is True
    assert orchestrator.calls[0]["kind"] == "private"
    assert orchestrator.calls[0]["conversation_id"] == "42"
    assert adapter.private_sends == []


async def test_send_without_orchestrator_or_hub_is_rejected():
    """既没有编排器也没有通知中心时不能假装成功。"""
    skill = CrossChatSkill(adapter=FakeAdapter())

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi",
    }))

    assert result["ok"] is False
    assert "投递不可用" in result["error"]


async def test_send_start_failure_reported():
    skill = CrossChatSkill(orchestrator=FakeOrchestrator(boom=True))

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi",
    }))

    assert result["ok"] is False
    assert "pipeline refused" in result["error"]


async def test_busy_target_falls_back_to_hub_injection_without_reply_attribution():
    """目标管线正忙时退化为通知注入，且不谎报拿得到回复。"""
    hub = FakeHub()
    skill = CrossChatSkill(notification_hub=hub, orchestrator=FakeOrchestrator(None))

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi", "mode": "wait",
    }))

    assert result["ok"] is True
    assert result["status"] == "delegated"
    assert "无法归属" in result["detail"]
    assert hub.published[0]["content"] == "hi"
    assert hub.published[0]["conversation_id"] == "888"


async def test_invalid_target_kind_rejected():
    skill = CrossChatSkill(orchestrator=FakeOrchestrator(FakeEvent()))

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "channel", "target_id": "888", "task": "hi",
    }))

    assert result["ok"] is False
    assert "target_kind" in result["error"]


# ── 旧式标记兜底：不能再进任务正文 ──────────────────────────────────────────


def test_leading_markers_are_extracted_and_removed():
    text, markers = extract_leading_markers(
        "[mode: fire_and_forget] [notify: no_response] 告知群123456：交作业"
    )
    assert text == "告知群123456：交作业"
    assert markers == {"mode": "fire_and_forget", "notification_mode": "no_response"}


def test_leading_markers_do_not_eat_ordinary_prose():
    for phrase in ("[mode: 是什么] 这是正常句子", "cancel 是什么意思", "记得交作业"):
        text, markers = extract_leading_markers(phrase)
        assert text == phrase and markers == {}


async def test_markers_in_task_are_used_as_fallback_and_stripped():
    orchestrator = FakeOrchestrator(FakeEvent())
    skill = CrossChatSkill(orchestrator=orchestrator)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888",
        "task": "[mode: wait] [notify: response] 告知群里交作业",
        "pipeline_key": "group:111",
    }))

    assert result["ok"] is True
    assert result["mode"] == "wait"
    assert result["notification_mode"] == "response"
    # 标记不能出现在交给目标 agent 的正文里
    assert orchestrator.calls[0]["content"] == "告知群里交作业"


async def test_task_with_only_markers_rejected():
    skill = CrossChatSkill(orchestrator=FakeOrchestrator(FakeEvent()))

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "[mode: wait]",
    }))

    assert result["ok"] is False
    assert "没有实际内容" in result["error"]


# ── 结果回传 ────────────────────────────────────────────────────────────────


async def test_wait_mode_returns_target_agent_reply():
    orchestrator = FakeOrchestrator(FakeEvent("明天十点，收到"))
    skill = CrossChatSkill(orchestrator=orchestrator)

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "问一下集合时间",
        "mode": "wait", "pipeline_key": "group:111",
    }))

    assert result["ok"] is True
    assert result["status"] == "responded"
    assert result["reply"] == "明天十点，收到"


async def test_wait_mode_times_out_without_faking_a_reply():
    skill = CrossChatSkill(
        orchestrator=FakeOrchestrator(FakeEvent(terminal=False)), wait_timeout_seconds=0.01,
    )

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "hi", "mode": "wait",
    }))

    assert result["ok"] is True
    assert result["status"] == "timeout"
    assert "reply" not in result


async def test_fire_and_forget_response_relays_reply_to_origin():
    hub = FakeHub()
    skill = CrossChatSkill(
        notification_hub=hub, orchestrator=FakeOrchestrator(FakeEvent("收到，明天见")),
    )

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "通知一下",
        "notification_mode": "response", "pipeline_key": "group:111",
    }))
    assert result["status"] == "delivered"

    await _drain_watchers(skill)

    relay = [item for item in hub.published if "跨聊天回复" in item["content"]]
    assert len(relay) == 1
    assert relay[0]["kind"] == "group" and relay[0]["conversation_id"] == "111"
    assert "收到，明天见" in relay[0]["content"]


async def test_no_response_never_relays():
    hub = FakeHub()
    skill = CrossChatSkill(
        notification_hub=hub, orchestrator=FakeOrchestrator(FakeEvent("收到")),
    )

    await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "通知一下",
        "pipeline_key": "group:111",
    })
    await asyncio.sleep(0.05)

    assert skill._watchers == set()
    assert hub.published == []


async def test_wait_with_response_also_relays_to_origin():
    hub = FakeHub()
    skill = CrossChatSkill(
        notification_hub=hub, orchestrator=FakeOrchestrator(FakeEvent("好的")),
    )

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "问一下",
        "mode": "wait", "notification_mode": "response", "pipeline_key": "private:9",
    }))

    assert result["reply"] == "好的"
    assert result["relayed"] is True
    assert hub.published[0]["kind"] == "private" and hub.published[0]["conversation_id"] == "9"


async def test_forged_pipeline_key_is_not_trusted_for_relay():
    """pipeline_key 非法时不做回传，而不是发到奇怪的目标。"""
    hub = FakeHub()
    skill = CrossChatSkill(
        notification_hub=hub, orchestrator=FakeOrchestrator(FakeEvent("好的")),
    )

    result = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "问一下",
        "mode": "wait", "notification_mode": "response", "pipeline_key": "not-a-key",
    }))

    assert result["reply"] == "好的"
    assert "relayed" not in result
    assert hub.published == []


# ── 状态 ────────────────────────────────────────────────────────────────────


async def test_status_reports_tracked_task():
    skill = CrossChatSkill(orchestrator=FakeOrchestrator(FakeEvent("好的")))

    sent = _parse(await skill.execute("cross_chat_send", {
        "target_kind": "group", "target_id": "888", "task": "q", "mode": "wait",
    }))
    status = _parse(await skill.execute("cross_chat_status", {"task_id": sent["task_id"]}))

    assert status["status"] == "responded"
    assert status["reply"] == "好的"
    assert status["target"] == "group:888"


async def test_status_with_unknown_task_id():
    skill = CrossChatSkill()

    result = _parse(await skill.execute("cross_chat_status", {"task_id": "t1"}))

    assert result["ok"] is True
    assert result["status"] == "unknown"


async def test_status_without_task_id_lists_tasks():
    skill = CrossChatSkill()

    result = _parse(await skill.execute("cross_chat_status", {}))

    assert result["ok"] is True
    assert result["active_tasks"] == 0
    assert result["tasks"] == []


# ── 查询 ────────────────────────────────────────────────────────────────────


async def test_query_uses_cached_queue_text():
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
    skill = CrossChatSkill(adapter=FakeAdapter(), group_message_queue=None, friend_message_queue=None)

    result = _parse(await skill.execute("cross_chat_query", {
        "target_kind": "private", "target_id": "42", "query": "q",
    }))

    assert result["ok"] is False
    assert "消息队列未配置" in result["error"]


async def test_query_adapter_error_reported():
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


async def test_unknown_tool_returns_error():
    skill = CrossChatSkill()

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown cross_chat tool" in result["error"]
