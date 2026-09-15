"""盲审发现的问题的回归锁定（每条都对应一次实测失败）。

这些用例的价值在于：它们是**第三方盲审跑出来的**，现有单测当时一条都没覆盖
（审查结论原话：“HEAD 自测全绿，下列问题一条都没被现有测试覆盖”）。
每条都注明「若回退会怎样」，避免以后被当成冗余用例删掉。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_contracts.models import ConversationRef

from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.output_guard import clean_text, should_drop
from neobot_app.reply.sender import ReplySender, SelfSentSink
from neobot_app.reply.tools import ReplyToolExecutor

BOT_QQ = 10001
USER_QQ = 30001
GROUP = "888888"
NAME = "AAA大肥鱼"
FENCE = chr(96) * 3
NO_TS = 10_000_000


class FakeAdapter:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, conversation_ref, payload, wait_response: bool = True) -> dict:
        self.sent.append(payload)
        return {"status": "ok", "message_id": 1}


class FakeFileServer:
    _enabled = False

    def register_file(self, path) -> str:
        return f"file:///{path}"


class ExplodingUowFactory:
    def __call__(self):
        raise RuntimeError("no db")


class StageRewriter:
    """按 stage 改写 runtime envelope 的假插件。"""

    def __init__(self, stage: str, patch: dict) -> None:
        self.stage = stage
        self.patch = patch

    async def dispatch_envelope(self, envelope):
        if envelope.stage == self.stage:
            envelope.payload.update(self.patch)
        return envelope


def _sender(**overrides):
    adapter = FakeAdapter()
    sender = ReplySender(
        adapter=adapter,
        file_server=FakeFileServer(),
        config=SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ)),
        bot_name=NAME,
        self_sent_uow_factory=ExplodingUowFactory(),
        **overrides,
    )
    return sender, adapter


def _event():
    event = ReplyEvent(conversation_ref=ConversationRef(kind="group", id=GROUP))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _queue():
    return MessageQueue(max_size=50, timestamp_interval_seconds=NO_TS, bot_account=BOT_QQ)


def _user_message(message_id: int, text: str, nickname: str = "贝拉") -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=USER_QQ,
        group_id=int(GROUP),
        sender=PostMessageMessagesender(user_id=USER_QQ, nickname=nickname),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def _bot_message(message_id: int, text: str) -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=BOT_QQ,
        group_id=int(GROUP),
        sender=PostMessageMessagesender(user_id=BOT_QQ, nickname=NAME),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def _wire(adapter) -> list[list[str]]:
    return [
        [seg.get("data", {}).get("text", seg.get("type")) for seg in payload]
        for payload in adapter.sent
    ]


# ── A. 生产名字集合必须覆盖「别人」（报告主症状） ─────────────────


async def test_headline_symptom_is_stripped_with_production_names() -> None:
    """回退后果：「215: 贝拉: 要抱抱」被按空格切成三条发出，并写回历史继续示范。"""
    queue = _queue()
    queue.push(GROUP, _user_message(11, "在吗"))
    queue.push(GROUP, _bot_message(-1, "在的"))

    names = MessageNumbering(bot_account=BOT_QQ, queue=queue).known_sender_names()
    sender, adapter = _sender()
    await sender.send_reply(
        _event(),
        "215: 贝拉: 要抱抱",
        self_sent=SelfSentSink(queue=queue, snapshot=queue, queue_key=GROUP),
        sender_names=names,
    )

    assert _wire(adapter) == [["要抱抱"]]
    assistant = [
        m["content"]
        for m in build_role_messages(queue, GROUP, bot_account=BOT_QQ)
        if m["role"] == "assistant"
    ]
    assert assistant[-1] == "要抱抱"


# ── B. 缩进：清洗不得改写正文排版 ────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "def f():\n    return 1",
        "看：" + FENCE + "python\ndef f():\n    return 1\n" + FENCE,
        "- a\n  - b",
    ],
)
def test_text_layout_is_preserved(text: str) -> None:
    """回退后果：清洗无条件 lstrip 每一行，代码块缩进被压平（markdown 转图错版）。"""
    assert clean_text(text, known_sender_names=[NAME]) == text


async def test_send_original_keeps_indentation() -> None:
    """回退后果：send_original=True 名义上发原文，实际发出去的是压平版。"""
    sender, adapter = _sender()
    await sender.send_reply(_event(), "对齐一下：\n    第一列\n    第二列", send_original=True)
    assert _wire(adapter) == [["对齐一下：\n    第一列\n    第二列"]]


# ── C. 标点回复不得被当成残渣吞掉 ────────────────────────────────


@pytest.mark.parametrize("body", ["？？？", "。。。", "(^_^)"])
def test_punctuation_reply_survives_prefix_stripping(body: str) -> None:
    """回退后果：带前缀的「？？？」被静默吞掉，用户什么都收不到。"""
    raw = f"{NAME}: {body}"
    cleaned = clean_text(raw, known_sender_names=[NAME])
    assert cleaned == body
    assert should_drop(raw, cleaned, known_sender_names=[NAME]) is False


# ── D. 插件改写 / 各发送组合都不能绕过兜底 ───────────────────────


async def test_plugin_send_before_rewrite_is_resanitised() -> None:
    """回退后果：插件在 reply.send.before 写回的脏文本绕过兜底直通线上。"""
    events = StageRewriter(
        "reply.send.before",
        {"text": f"193: {NAME}: 我是一条鱼", "segments": ["正常"], "send_original": True},
    )
    sender, adapter = _sender(debug_helper=DebugHelper(runtime_events=events))
    await sender.send_reply(_event(), "原始", sender_names=[NAME])
    assert _wire(adapter) == [["我是一条鱼"]]


async def test_plugin_postprocess_after_rewrite_is_resanitised() -> None:
    """回退后果：reply.postprocess.after 的改写发生在清洗之后，脏文本直通线上。"""
    events = StageRewriter(
        "reply.postprocess.after",
        {"reply_messages": [f"193: {NAME}: 我是一条鱼"]},
    )
    sender, adapter = _sender(debug_helper=DebugHelper(runtime_events=events))
    await sender.send_reply(_event(), "原始", sender_names=[NAME])
    assert _wire(adapter) == [["我是一条鱼"]]


async def test_tool_layer_and_sender_agree_on_names() -> None:
    """回退后果：工具层只认识配置昵称、发送层认识群名片 → 静默缝（工具说已发，实际没发）。"""
    queue = _queue()
    queue.push(GROUP, _user_message(11, "在吗"))
    numbering = MessageNumbering(bot_account=BOT_QQ, queue=queue)

    sender, adapter = _sender()

    async def handler(**kwargs):
        return await sender.send_reply(
            _event(), kwargs["text"], segments=kwargs["segments"], sender_names=[NAME, "贝拉"]
        )

    executor = ReplyToolExecutor(send_reply_handler=handler, numbering=numbering, bot_name=NAME)
    result = await executor.execute("send_reply", {"text": "215: 贝拉: 要抱抱"})

    assert _wire(adapter) == [["要抱抱"]]
    assert "已发送" in result


# ── E. 写回历史的内容必须与真正发出的内容同源 ────────────────────


async def test_history_matches_what_was_actually_sent() -> None:
    """回退后果：工具层清一趟、发送层清另一趟 → 「已发送 X」与历史不一致。"""
    queue = _queue()
    sender, adapter = _sender()
    await sender.send_reply(
        _event(),
        f"{NAME}: [msg_id=909] 在的",
        self_sent=SelfSentSink(queue=queue, snapshot=queue, queue_key=GROUP),
        sender_names=[NAME],
    )
    assert _wire(adapter) == [["在的"]]
    assistant = [
        m["content"]
        for m in build_role_messages(queue, GROUP, bot_account=BOT_QQ)
        if m["role"] == "assistant"
    ]
    assert assistant == ["在的"]
