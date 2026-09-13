"""fix(2) 统一自身发言入队通道的回归用例。

对应 bugfixes/fix(2)-pipeline-rebuild-loses-self-reply/fix-plan.md §5：
F1（各发送类型都产生 assistant 条目）、F2（多段逐条）、F3/F18（图片索引、多图逐条）、
F4/F16（temp 图库可再次取回、清理后仍有 file: 兜底）、F5（重建后 assistant 块还在）、
F9（只入队一次）、F10（窗口占用 ≈ 索引长度）、F13（权重 0.1，两个来源一致）、
F17（语音保留原始文本 + 文件索引）、F14（通知入队并渲染）。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_contracts.models import ConversationRef

from neobot_app.message.queue import (
    MessageQueue,
    NotificationEntry,
    QueueEntryType,
)
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.sender import ReplySender, SelfSentSink

BOT_QQ = 10001
USER_QQ = 20001
GROUP_ID = "888888"
QUEUE_KEY = GROUP_ID

_NO_TIMESTAMP_INTERVAL = 10_000_000


class FakeAdapter:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, conversation_ref, payload, wait_response: bool = True) -> dict:
        self.sent.append(payload)
        return {"status": "ok", "message_id": 1001}


class FakeFileServer:
    _enabled = False

    def register_file(self, path) -> str:
        return f"file:///{path.as_posix()}"


class FakeEmojiEntry:
    def __init__(self, file_path) -> None:
        self.file_path = file_path


class FakeEmojiService:
    """只提供发送路径需要的 get_entry / record_usage。"""

    def __init__(self, paths: dict[int, object]) -> None:
        self._paths = paths
        self.used: list[int] = []

    def get_entry(self, number: int):
        path = self._paths.get(number)
        return FakeEmojiEntry(path) if path is not None else None

    async def record_usage(self, number: int) -> None:
        self.used.append(number)


class FakeRegistrar:
    """模拟 CreatorImageService.register_local_image 的返回（记录收到的路径）。"""

    def __init__(self, image_id: str | None = "tmp_abc123456789") -> None:
        self.image_id = image_id
        self.calls: list = []

    async def __call__(self, file_path):
        self.calls.append(file_path)
        if self.image_id is None:
            return None
        return SimpleNamespace(image_id=self.image_id)


class ExplodingRegistrar:
    async def __call__(self, file_path):
        raise RuntimeError("temp 图库不可用")


class ExplodingUowFactory:
    """落盘入口抛异常：用例只关心入队，绝不能顺手写真实数据库。"""

    def __call__(self):
        raise RuntimeError("数据库不可用")


def _event(kind: str = "group", conv_id: str = GROUP_ID) -> ReplyEvent:
    event = ReplyEvent(conversation_ref=ConversationRef(kind=kind, id=conv_id))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _user_message(message_id: int, text: str) -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=USER_QQ,
        group_id=int(GROUP_ID),
        sender=PostMessageMessagesender(user_id=USER_QQ, nickname="群友"),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def _make_sender(**overrides) -> tuple[ReplySender, FakeAdapter]:
    adapter = FakeAdapter()
    config = SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ))
    overrides.setdefault("self_sent_uow_factory", ExplodingUowFactory())
    sender = ReplySender(
        adapter=adapter,
        file_server=FakeFileServer(),
        config=config,
        bot_name="测试机器人",
        **overrides,
    )
    return sender, adapter


def _make_queue(**kwargs) -> MessageQueue:
    params = {
        "max_size": 100,
        "timestamp_interval_seconds": _NO_TIMESTAMP_INTERVAL,
        "bot_account": BOT_QQ,
    }
    params.update(kwargs)
    return MessageQueue(**params)


def _sink(queue: MessageQueue, snapshot=None) -> SelfSentSink:
    # 注意：MessageQueue 定义了 __len__，空队列是 falsy，不能用 "or" 做默认值。
    return SelfSentSink(
        queue=queue,
        snapshot=queue if snapshot is None else snapshot,
        queue_key=QUEUE_KEY,
    )


def _assistant_texts(queue: MessageQueue) -> list[str]:
    messages = build_role_messages(queue, QUEUE_KEY, bot_account=BOT_QQ)
    return [m["content"] for m in messages if m["role"] == "assistant"]


def _message_entries(queue: MessageQueue) -> list:
    return [
        entry
        for entry in queue.entries(QUEUE_KEY)
        if entry.kind == QueueEntryType.MESSAGE
    ]


# ── 根因锁定：只有用户消息 ⇒ 没有 assistant 块 ───────────────────


def test_queue_with_only_user_messages_has_no_assistant_block() -> None:
    """只要 Bot 自己的发言没进队列，重建出的 transcript 就没有 assistant 块。"""
    queue = _make_queue()
    queue.push(QUEUE_KEY, _user_message(1, "在吗"))

    assert _assistant_texts(queue) == []


# ── F5 / F1 / F9：真实发送点自动入队，重建后 assistant 块还在 ─────


async def test_send_reply_enqueues_text_once_and_survives_rebuild() -> None:
    """回复 A → 管线寿命归零后重建：第二次请求仍包含 assistant 块且含 A。

    同时锁 F9：一次发送只入队一条（手工补记与自动入队不得叠加）。
    """
    sender, adapter = _make_sender()
    queue = _make_queue()
    queue.push(QUEUE_KEY, _user_message(1, "在吗"))
    event = _event()

    await sender.send_reply(event, "在的", self_sent=_sink(queue))

    assert len(adapter.sent) == 1
    entries = _message_entries(queue)
    assert len(entries) == 2  # 1 条用户消息 + 1 条自身发言，只入队一次
    assistant = _assistant_texts(queue)
    assert len(assistant) == 1
    assert "在的" in assistant[0]


async def test_multi_segment_reply_enqueues_each_real_sentence() -> None:
    """F2：多段文本按真正发到 QQ 的多条语句逐条入队，顺序与内容一致。"""
    sender, adapter = _make_sender()
    queue = _make_queue()
    event = _event()

    await sender.send_reply(
        event, "ignored", segments=["第一句", "第二句"], self_sent=_sink(queue)
    )

    assert len(adapter.sent) == 2
    assistant = _assistant_texts(queue)
    assert len(assistant) == 2
    assert "第一句" in assistant[0]
    assert "第二句" in assistant[1]


async def test_nested_queue_snapshot_also_receives_self_sent() -> None:
    """源队列与管线快照必须同步收到，否则同一管线内的 diff 会把它当新消息。"""
    sender, _ = _make_sender()
    queue = _make_queue()
    snapshot = queue.clone(QUEUE_KEY)
    event = _event()

    await sender.send_reply(event, "在的", self_sent=_sink(queue, snapshot))

    assert len(_message_entries(queue)) == 1
    assert len(_message_entries(snapshot)) == 1


# ── F3 / F18：图片是索引，且逐张各一条 ───────────────────────────


async def test_image_reply_enqueues_one_index_per_image(tmp_path) -> None:
    """F18：一次回复发 N 张图 ⇒ N 条图片索引条目，顺序与发送顺序一致。"""
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    registrar = FakeRegistrar("tmp_first")
    sender, _ = _make_sender(image_registrar=registrar)
    emoji = FakeEmojiService({1: first, 2: second})
    sender._emoji_service = emoji
    queue = _make_queue()
    event = _event()

    await sender.send_reply(event, "", images=[1, 2], self_sent=_sink(queue))

    index_entries = [
        entry
        for entry in _message_entries(queue)
    ]
    texts = [
        entry.message.raw_message
        for entry in index_entries
        if entry.message is not None and "[图片:" in entry.message.raw_message
    ]
    assert len(texts) == 2
    assert "tmp_first" in texts[0]
    assert "tmp_first" in texts[1]
    assert [str(p) for p in registrar.calls] == [str(first), str(second)]


async def test_markdown_reply_enqueues_index_without_full_text(tmp_path) -> None:
    """F3/F10：Markdown 转图只留索引 + 前 N 字来源标注，不重复注入全文。"""
    png = tmp_path / "rendered.png"
    png.write_bytes(b"png-data")
    registrar = FakeRegistrar("tmp_md123")
    sender, _ = _make_sender(image_registrar=registrar)
    queue = _make_queue()
    event = _event()

    long_text = "第一段内容。" * 400
    await sender.record_self_sent_image(
        _sink(queue),
        event.conversation_ref,
        png,
        kind="markdown",
        source_note=long_text,
    )

    entries = _message_entries(queue)
    assert len(entries) == 1
    raw = entries[0].message.raw_message
    assert raw.startswith("[Markdown图片:tmp_md123 file:")
    assert long_text not in raw
    # F10：窗口占用 ≈ 索引长度，远小于 Markdown 全文
    assert len(raw) < 400 < len(long_text)


async def test_image_index_falls_back_to_file_when_registrar_missing(tmp_path) -> None:
    """F16：temp 图库不可用时仍写 file: 路径兜底（不出现死索引）。"""
    png = tmp_path / "orphan.png"
    png.write_bytes(b"x")
    sender, _ = _make_sender(image_registrar=ExplodingRegistrar())
    queue = _make_queue()
    event = _event()

    await sender.record_self_sent_image(
        _sink(queue), event.conversation_ref, png
    )

    raw = _message_entries(queue)[0].message.raw_message
    assert raw.startswith("[图片:file:")
    assert str(png) in raw


# ── F13：权重 0.1（实时入队与历史灌入同权重） ────────────────────


async def test_self_sent_text_occupies_point_one_weight() -> None:
    sender, _ = _make_sender()
    queue = _make_queue()
    event = _event()

    before = queue._weighted_counts.get(QUEUE_KEY, 0.0)
    await sender.send_reply(event, "在的", self_sent=_sink(queue))
    after = queue._weighted_counts[QUEUE_KEY]

    assert after - before == 0.1


def test_history_pushed_self_message_uses_same_weight() -> None:
    """F13：历史灌入的自身发言与实时入队同权重（同一发送者一个口径）。"""
    queue = _make_queue()
    queue.push_history(QUEUE_KEY, _user_message(1, "用户消息"))
    bot_message = GroupMessage(
        message_id=-999,
        user_id=BOT_QQ,
        group_id=int(GROUP_ID),
        sender=PostMessageMessagesender(user_id=BOT_QQ, nickname="测试机器人"),
        message=[MessageSegment(type="text", data={"text": "历史自身发言"})],
        raw_message="历史自身发言",
    )
    queue.push_history(QUEUE_KEY, bot_message)

    assert queue._weighted_counts[QUEUE_KEY] == 1.1


def test_self_sent_weight_is_configurable_and_clamped() -> None:
    assert _make_queue(self_sent_weight=0.25).self_sent_weight == 0.25
    assert _make_queue(self_sent_weight=5).self_sent_weight == 1.0
    assert _make_queue(self_sent_weight=-1).self_sent_weight == 0.0
    assert _make_queue(self_sent_weight=0.3).clone(QUEUE_KEY).self_sent_weight == 0.3


# ── F17：语音条目 ───────────────────────────────────────────────


async def test_voice_entry_keeps_original_text_and_file_index() -> None:
    """F17：语音暂无解析能力 ⇒ 保留发送时的原始文本 + 音频文件索引。"""
    sender, _ = _make_sender()
    queue = _make_queue()
    conv = ConversationRef(kind="group", id=GROUP_ID)

    await sender.record_self_sent_voice(
        _sink(queue), conv, "我说了句话", file_hint="/tmp/tts_1.mp3"
    )

    raw = _message_entries(queue)[0].message.raw_message
    assert raw.startswith("[语音:file:/tmp/tts_1.mp3]")
    assert "我说了句话" in raw


# ── F14：通知入队并渲染 ─────────────────────────────────────────


def test_notification_entry_renders_as_notice_block() -> None:
    queue = _make_queue()
    queue.push_notification(
        QUEUE_KEY, NotificationEntry(source="drawing", content="绘图完成")
    )

    messages = build_role_messages(queue, QUEUE_KEY, bot_account=BOT_QQ)
    assert messages == [{"role": "user", "content": "[通知:drawing] 绘图完成"}]


def test_notification_entry_uses_low_weight() -> None:
    queue = _make_queue()
    queue.push_notification(QUEUE_KEY, NotificationEntry(source="balance", content="余额不足"))

    assert queue._weighted_counts[QUEUE_KEY] == 0.1
    assert queue.size(QUEUE_KEY) == 1

# ── F14：编排器把通知写进正确的会话队列 ─────────────────────────


def _bare_orchestrator(group_queue, friend_queue):
    """只挂队列与日志的裸编排器（不跑 __init__ 的重型装配）。"""
    from neobot_app.reply.orchestrator import ReplyOrchestrator

    orchestrator = object.__new__(ReplyOrchestrator)
    orchestrator._group_queue = group_queue
    orchestrator._friend_queue = friend_queue
    from neobot_contracts.ports.logging import NullLogger

    orchestrator._logger = NullLogger()
    return orchestrator


def test_record_notification_routes_group_and_private_queues() -> None:
    group_queue = _make_queue()
    friend_queue = _make_queue(max_size=50)
    orchestrator = _bare_orchestrator(group_queue, friend_queue)

    assert orchestrator.record_notification(
        kind="group", conversation_id=GROUP_ID, source="drawing", content="图好了"
    )
    assert orchestrator.record_notification(
        kind="private", conversation_id="30001", source="balance", content="余额不足"
    )

    group_messages = build_role_messages(group_queue, GROUP_ID, bot_account=BOT_QQ)
    assert group_messages == [{"role": "user", "content": "[通知:drawing] 图好了"}]
    friend_messages = build_role_messages(friend_queue, "30001", bot_account=BOT_QQ)
    assert friend_messages == [{"role": "user", "content": "[通知:balance] 余额不足"}]


def test_record_notification_ignores_missing_queue_or_key() -> None:
    orchestrator = _bare_orchestrator(None, None)
    assert (
        orchestrator.record_notification(
            kind="group", conversation_id="1", source="x", content="y"
        )
        is False
    )

