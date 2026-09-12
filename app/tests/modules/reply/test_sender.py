"""ReplySender 测试：插件 consumed 路径、超时、长回复降级、消息段构建边界。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.sender import ReplySender


class FakeAdapter:
    """记录 send/call_api 调用的假适配器。"""

    def __init__(self) -> None:
        self.sent: list = []
        self.api_calls: list = []
        self.wait_responses: list[bool] = []

    async def send(
        self, conversation_ref: ConversationRef, payload: object, wait_response: bool = True
    ) -> dict:
        self.sent.append(payload)
        self.wait_responses.append(wait_response)
        return {"status": "ok", "message_id": 1001}

    async def call_api(self, action: str, params: dict) -> dict:
        self.api_calls.append((action, params))
        return {"status": "ok"}


class FakeFileServer:
    """未启用（file:/// 直发）的假文件服务。"""

    _enabled = False

    def register_file(self, path: Path) -> str:
        return f"file:///{path.as_posix()}"


class FakeRuntimeEvents:
    """按 stage 名决定是否 consume 的假运行时事件分发器。"""

    def __init__(self, consume_stages: set[str], result: object = "consumed") -> None:
        self._consume_stages = consume_stages
        self._result = result

    async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
        if envelope.stage in self._consume_stages:
            envelope.consume(self._result)
        return envelope


class FakeConverter:
    """可配置成功/失败/挂起的 Markdown 转图片假转换器。"""

    def __init__(self, *, result: Path | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def convert(self, markdown_text: str) -> Path:
        if self._error is not None:
            raise self._error
        return self._result


def _event_in_sending_ready_state(kind: str, conv_id: str) -> ReplyEvent:
    """构造已处于 GENERATING（发送前合法状态）的事件，模拟 orchestrator 的调用时序。"""
    event = ReplyEvent(conversation_ref=ConversationRef(kind=kind, id=conv_id))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _make_private_event() -> ReplyEvent:
    return _event_in_sending_ready_state("private", "123456")


def _make_group_event() -> ReplyEvent:
    return _event_in_sending_ready_state("group", "888888")


def _make_sender(**overrides) -> tuple[ReplySender, FakeAdapter]:
    adapter = FakeAdapter()
    sender = ReplySender(adapter=adapter, file_server=FakeFileServer(), **overrides)
    return sender, adapter


# ── send_with_timeout ────────────────────────────────────────────


async def test_send_with_timeout_returns_consumed_result_without_calling_adapter():
    """插件在 message.send.before 阶段 consume 后，必须直接返回 result 且不调用 adapter.send。"""
    events = FakeRuntimeEvents(consume_stages={"message.send.before"}, result="plugin-blocked")
    sender, adapter = _make_sender(runtime_events=events)

    result = await sender.send_with_timeout(ConversationRef(kind="private", id="1"), {"type": "text"})

    assert result == "plugin-blocked"
    assert adapter.sent == []


async def test_send_with_timeout_calls_adapter_send_when_not_consumed():
    """未被插件 consume 时，必须调用 adapter.send 并返回其结果。"""
    sender, adapter = _make_sender()

    result = await sender.send_with_timeout(ConversationRef(kind="private", id="1"), {"type": "text"})

    assert len(adapter.sent) == 1
    assert result == {"status": "ok", "message_id": 1001}


async def test_send_with_timeout_raises_when_adapter_hangs():
    """adapter.send 挂起超过 io_timeout_seconds 时必须抛 asyncio.TimeoutError。"""
    class _HangingAdapter(FakeAdapter):
        async def send(self, conversation_ref, payload, wait_response: bool = True):
            await asyncio.sleep(60)
            return {}

    sender = ReplySender(
        adapter=_HangingAdapter(),
        file_server=FakeFileServer(),
        io_timeout_seconds=0.05,
    )

    with pytest.raises(asyncio.TimeoutError):
        await sender.send_with_timeout(ConversationRef(kind="private", id="1"), {"type": "text"})


# ── build_reply_segments 段构建边界 ──────────────────────────────


def test_build_reply_segments_group_with_mention_and_reply():
    """群聊中同时指定 mention 与 reply_to 时，段顺序必须为 at → reply → text。"""
    segments = ReplySender.build_reply_segments(
        text="你好",
        conversation_kind="group",
        reply_to_message_id=42,
        mention_user_ids=[111, 222],
    )
    assert [s["type"] for s in segments] == ["at", "at", "reply", "text"]
    assert segments[0]["data"]["qq"] == "111"
    assert segments[2]["data"]["id"] == "42"
    assert segments[3]["data"]["text"] == "你好"


def test_build_reply_segments_private_ignores_mention():
    """私聊中指定 mention 时不得生成 at 段（仅 reply + text）。"""
    segments = ReplySender.build_reply_segments(
        text="在的",
        conversation_kind="private",
        reply_to_message_id=7,
        mention_user_ids=[111],
    )
    assert [s["type"] for s in segments] == ["reply", "text"]


def test_build_reply_segments_plain_text_only():
    """无 mention 无 reply_to 时只生成 text 段，且为空字符串时仍保留 text 段。"""
    segments = ReplySender.build_reply_segments(text="", conversation_kind="group")
    assert segments == [{"type": "text", "data": {"text": ""}}]


# ── _build_reply_messages 文本分支 ───────────────────────────────


def test_build_reply_messages_send_original_returns_stripped_text():
    """send_original=True 时返回原文（去除首尾空白），不做任何切分。"""
    sender, _ = _make_sender()
    messages = sender._build_reply_messages("  我就爱说这么多句话。 ", send_original=True)
    assert messages == ["我就爱说这么多句话。"]


def test_build_reply_messages_uses_cleaned_segments():
    """提供 segments 时返回清洗后的非空条目；全空/空白 segments 必须回退到切分逻辑。"""
    sender, _ = _make_sender()
    messages = sender._build_reply_messages("ignored", segments=["  第一句  ", "", "   ", "第二句"])
    assert messages == ["第一句", "第二句"]


def test_build_reply_messages_fallback_on_long_text():
    """超长文本（超过 max_length）必须触发默认回复降级，返回单条 fallback 文本。"""
    sender, _ = _make_sender(long_reply_max_length=10, bot_name="测试机器人")
    long_text = "这是一句特别特别特别特别特别特别特别特别特别特别长的回复内容。"
    messages = sender._build_reply_messages(long_text)
    assert len(messages) == 1
    assert "懒得和你说道理" in messages[0]


# ── send_reply 完整发送路径 ──────────────────────────────────────


async def test_send_reply_consumed_before_send_returns_early():
    """reply.send.before 被插件 consume 后 send_reply 必须静默返回并设置 send_response，不调用 adapter。"""
    events = FakeRuntimeEvents(consume_stages={"reply.send.before"}, result="handled-by-plugin")
    debug_helper = DebugHelper(runtime_events=events)
    sender, adapter = _make_sender(debug_helper=debug_helper)
    event = _make_group_event()

    await sender.send_reply(event, "你好")

    assert event.send_response == "handled-by-plugin"
    assert adapter.sent == []


async def test_send_reply_falls_back_to_text_when_markdown_render_fails():
    """长回复 Markdown 渲染失败（converter 抛异常）时必须降级为文本发送且不抛异常。"""
    converter = FakeConverter(error=RuntimeError("render boom"))
    sender, adapter = _make_sender(markdown_image_converter=converter, long_reply_max_length=10)
    event = _make_private_event()
    long_text = "这是一段特别特别特别特别特别特别特别特别特别特别长的回复。你被降级了。"

    await sender.send_reply(event, long_text)

    assert adapter.sent, "降级后必须调用 adapter.send 发送文本"
    sent_payload = adapter.sent[0]
    assert isinstance(sent_payload, list)
    assert sent_payload[0]["type"] == "text"
    assert event.state == ReplyState.GENERATING


async def test_send_reply_uses_markdown_image_when_render_succeeds(tmp_path):
    """Markdown 渲染成功时发送图片段（不发送文本），并记录 send_response。"""
    png = tmp_path / "rendered.png"
    png.write_bytes(b"png-data")
    converter = FakeConverter(result=png)
    sender, adapter = _make_sender(
        markdown_image_converter=converter,
        long_reply_max_length=10,
        emoji_service=None,
    )
    event = _make_private_event()
    long_text = "这是一段特别特别特别特别特别特别特别特别特别特别长的回复。"

    await sender.send_reply(event, long_text)

    assert len(adapter.sent) == 1
    assert adapter.sent[0][0]["type"] == "image"
    assert event.send_response == {"status": "ok", "message_id": 1001}


async def test_send_reply_plain_short_text_single_send():
    """普通短文本走切分发送路径，只调用一次 adapter.send 且事件状态正确推进。"""
    sender, adapter = _make_sender()
    event = _make_group_event()

    await sender.send_reply(event, "简单的回复")

    assert len(adapter.sent) == 1
    assert event.send_response == {"status": "ok", "message_id": 1001}
    assert event.state == ReplyState.COMPLETED


async def test_send_reply_does_not_wait_for_send_echo():
    """回复发送必须 wait_response=False：等 echo 只会白白阻塞 agent 循环。

    实测发送几乎不会失败，等待上游回执的收益远小于它带来的延迟。
    """
    sender, adapter = _make_sender()
    event = _make_group_event()

    await sender.send_reply(event, "简单的回复")

    assert adapter.wait_responses == [False]


async def test_second_group_send_reply_after_completed_still_delivers():
    """群聊同轮第二次 send_reply：事件已终态，不得抛「非法状态转换」，消息仍须送达。

    旧实现在 sender 里无条件 transition(SENDING)：COMPLETED 是终态，第二条
    send_reply 直接抛 RuntimeError，被编排器记成 tool_failed —— 第二条消息被吞，
    模型还被告知工具失败。终态下不再改状态，但仍把发送执行完。
    """
    sender, adapter = _make_sender()
    event = _make_group_event()

    await sender.send_reply(event, "第一条")
    assert event.state == ReplyState.COMPLETED

    await sender.send_reply(event, "第二条")

    assert len(adapter.sent) == 2
    assert event.state == ReplyState.COMPLETED


async def test_second_private_send_reply_keeps_event_generating():
    """私聊连续发送仍回到 GENERATING，管线可以继续下一轮。"""
    sender, adapter = _make_sender()
    event = _make_private_event()

    await sender.send_reply(event, "第一条")
    assert event.state == ReplyState.GENERATING

    await sender.send_reply(event, "第二条")

    assert len(adapter.sent) == 2
    assert event.state == ReplyState.GENERATING


async def test_send_reply_raises_when_conversation_ref_missing():
    """conversation_ref 为 None 时 send_reply 必须抛 ValueError（事件状态已推进到 GENERATING）。"""
    sender, _ = _make_sender()
    event = ReplyEvent()
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)

    with pytest.raises(ValueError, match="conversation_ref"):
        await sender.send_reply(event, "你好")


# ── 其他辅助 ─────────────────────────────────────────────────────


def test_can_use_markdown_image_false_without_converter():
    """未配置 markdown_image_converter 时 _can_use_markdown_image 必须返回 False。"""
    sender, _ = _make_sender()
    assert sender._can_use_markdown_image("随便什么文本") is False


async def test_call_api_with_timeout_forwards_action_and_params():
    """call_api_with_timeout 必须把 action/params 原样转发给 adapter.call_api。"""
    sender, adapter = _make_sender()
    result = await sender.call_api_with_timeout("group_poke", {"group_id": 1, "user_id": 2})
    assert adapter.api_calls == [("group_poke", {"group_id": 1, "user_id": 2})]
    assert result == {"status": "ok"}
