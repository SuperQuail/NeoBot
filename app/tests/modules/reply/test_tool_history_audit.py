"""发送工具历史记录审计（独立测试；可报告缺口，不改核心实现）。

覆盖 send_reply（文字/图片/表情包）、speak、send_long_reply、send_official_markdown
与后台通知：写回会话队列的内容，以及 role_messages 重建出的工具调用/回执。
所有用例断言当前契约；审计期发现的 numbering 负 msg_id 缺口已修复并转正。
审计结论与最小修复建议见 docs/audit-tool-history.md。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import neobot_app.reply.orchestrator_parts.agent_handlers as agent_handlers
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import NullLogger

from neobot_app.bot_accounts import bind_bot_accounts
from neobot_app.config.schemas.bot import Bot, BotConfig
from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.sender import ReplySender, SelfSentSink

GROUP_KEY = "42"
BOT_ACCOUNT = 10001
CHANNEL_ACCOUNT = 22222


# ── 假件 ────────────────────────────────────────────────────────────


class _Adapter:
    def __init__(self, result: object | None = None) -> None:
        self.calls: list[tuple[object, dict]] = []
        self.result = result if result is not None else {"status": "ok", "message_id": 9001}

    async def send(self, conversation, payload, wait_response=True, **kwargs):
        self.calls.append((payload, kwargs))
        return self.result


class _FileServer:
    _enabled = False

    def register_file(self, path) -> str:
        return f"file:///{Path(path).as_posix()}"


class _EmojiService:
    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)
        self.entries = {1: self.file_path}
        self.used: list[int] = []

    def get_entry(self, number: int):
        path = self.entries.get(number)
        return SimpleNamespace(file_path=path) if path is not None else None

    async def record_usage(self, number: int) -> None:
        self.used.append(number)


class _Uow:
    def __init__(self) -> None:
        self.messages = SimpleNamespace(save_message=AsyncMock())
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _UowFactory:
    def __init__(self) -> None:
        self.uows: list[_Uow] = []

    def __call__(self) -> _Uow:
        uow = _Uow()
        self.uows.append(uow)
        return uow


class _TtsService:
    enabled = True

    async def synthesize_segment(self, text: str):
        return {"type": "record", "data": {"file": "/tmp/voice.mp3"}}


@pytest.fixture(autouse=True)
def _reset_bot_accounts():
    bind_bot_accounts(None, None)
    yield
    bind_bot_accounts(None, None)


def _config(account: int = 0) -> BotConfig:
    config = BotConfig()
    config.bot = Bot(account=account)
    return config


def _sender(*, config=None, adapter=None, emoji=None, registrar=None, uow_factory=None) -> ReplySender:
    return ReplySender(
        adapter=adapter or _Adapter(),
        file_server=_FileServer(),
        config=config,
        bot_name="Bot",
        emoji_service=emoji,
        image_registrar=registrar,
        self_sent_uow_factory=uow_factory,
        logger=NullLogger(),
    )


def _event(*, bot_account: int = BOT_ACCOUNT, pre_reply_message_id=None) -> ReplyEvent:
    event = ReplyEvent(
        mode="agent",
        conversation_ref=ConversationRef(kind="group", id=GROUP_KEY),
        bot_account=bot_account,
        pre_reply_message_id=pre_reply_message_id,
    )
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _message_entries(queue: MessageQueue, key: str = GROUP_KEY) -> list:
    return [entry for entry in queue.entries(key) if entry.kind.value == "message"]


def _rebuilt(queue: MessageQueue, *, bot_account: int = BOT_ACCOUNT) -> list[dict]:
    return build_role_messages(queue, GROUP_KEY, bot_account=bot_account)


def _calls(messages: list[dict]) -> list[dict]:
    return [message["tool_calls"][0]["function"] for message in messages if message.get("tool_calls")]


def _results(messages: list[dict]) -> list[dict]:
    return [
        {**json.loads(message["content"]), "tool_call_id": message["tool_call_id"]}
        for message in messages
        if message.get("role") == "tool"
    ]


async def _drain(sender: ReplySender) -> None:
    tasks = list(sender._self_sent_persist_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _send_text(sender: ReplySender, queue: MessageQueue, text: str, *, bot_account: int = BOT_ACCOUNT) -> bool:
    return await sender.send_reply(
        _event(bot_account=bot_account),
        text,
        self_sent=SelfSentSink(queue=queue, snapshot=None, queue_key=GROUP_KEY),
    )


def _orchestrator(*, adapter=None, config=None, registrar=None, tts_service=None) -> ReplyOrchestrator:
    """只装配 agent 工具 handler 依赖的编排器（不跑真实循环）。"""
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._adapter = adapter or _Adapter()
    orch._file_server = _FileServer()
    orch._config = config
    orch._logger = NullLogger()
    orch._sender = _sender(config=config, adapter=orch._adapter, registrar=registrar, uow_factory=_UowFactory())
    orch._last_reply_time = {}
    orch._tts_service = tts_service
    orch._clear_unsent_marker = lambda event: None
    orch._record_reply_delivered = lambda *args, **kwargs: None
    return orch


def _group_message(message_id: int, *, user_id: int, self_id: int | None, text: str):
    from neobot_adapter.model.basic import PostMessageMessagesender
    from neobot_adapter.model.message import GroupMessage, MessageSegment, MessageTypeEnum

    return GroupMessage(
        message_type=MessageTypeEnum.group,
        message_id=message_id,
        self_id=self_id,
        user_id=user_id,
        group_id=42,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=PostMessageMessagesender(user_id=user_id, nickname=str(user_id)),
    )


# ── send_reply：文字 ────────────────────────────────────────────────


async def test_send_reply_text_writes_queue_rebuilds_tool_call_and_persists() -> None:
    """文字发送成功：队列 + tool_call 重建 + 落盘记录三者一致。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    uow_factory = _UowFactory()
    sender = _sender(config=_config(BOT_ACCOUNT), uow_factory=uow_factory)

    assert await _send_text(sender, queue, "你好呀") is True
    await _drain(sender)

    self_message = _message_entries(queue)[0].message
    assert self_message.message_id is not None and self_message.message_id < 0
    assert self_message.user_id == self_message.self_id == BOT_ACCOUNT

    rebuilt = _rebuilt(queue)
    calls, results = _calls(rebuilt), _results(rebuilt)
    assert [(call["name"], json.loads(call["arguments"])) for call in calls] == [("send_reply", {"text": "你好呀"})]
    call_ids = [message["tool_calls"][0]["id"] for message in rebuilt if message.get("tool_calls")]
    assert results[0]["ok"] is True
    assert results[0]["tool_call_id"] == call_ids[0]

    saved = uow_factory.uows[0].messages.save_message.await_args.args[0]
    assert saved.event_id == f"self:{self_message.message_id}"
    assert saved.sender_id == str(BOT_ACCOUNT) and saved.text == "你好呀"


async def test_send_reply_text_failure_is_not_recorded() -> None:
    """文字发送失败：不写队列（避免历史声称已回复）。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    sender = _sender(config=_config(BOT_ACCOUNT), adapter=_Adapter({"status": "failed"}))

    assert await _send_text(sender, queue, "发不出去") is False
    await _drain(sender)
    assert _message_entries(queue) == []


# ── send_reply：图片 / 表情包（sticker） ───────────────────────────


async def test_send_reply_image_records_index_and_rebuilds_emoji_numbers(tmp_path) -> None:
    """图片成功：队列留索引（图库 id + file 路径），重建出 emoji_numbers + 图片索引回执。"""
    image = tmp_path / "a.png"
    image.write_bytes(b"png")
    queue = MessageQueue(bot_account=BOT_ACCOUNT)

    async def registrar(path):
        return SimpleNamespace(image_id="tmp_abc123")

    sender = _sender(config=_config(BOT_ACCOUNT), emoji=_EmojiService(image), registrar=registrar)
    assert (
        await sender.send_reply(
            _event(),
            "",
            images=[1],
            self_sent=SelfSentSink(queue=queue, snapshot=None, queue_key=GROUP_KEY),
        )
        is True
    )
    await _drain(sender)

    entries = _message_entries(queue)
    index_text = entries[0].message.raw_message
    assert index_text.startswith("[图片:tmp_abc123 file:")
    assert [segment.type for segment in entries[0].message.message] == ["text"]

    calls, results = _calls(_rebuilt(queue)), _results(_rebuilt(queue))
    assert json.loads(calls[0]["arguments"]) == {"emoji_numbers": [1]}
    assert results[0]["image_index"] == index_text


# ── speak ──────────────────────────────────────────────────────────


async def test_speak_records_voice_and_rebuilds_speak_tool_call() -> None:
    """语音：写回语音索引 + 事件通道账号；重建出 speak 调用与文件索引回执。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    orch = _orchestrator(config=_config(BOT_ACCOUNT), tts_service=_TtsService())

    await orch._agent_speak_handler(
        SimpleNamespace(reply_sent=False),
        _event(bot_account=CHANNEL_ACCOUNT),
        queue,
        queue,
        GROUP_KEY,
        "念这句话",
    )
    await _drain(orch._sender)

    entry = _message_entries(queue)[0]
    assert entry.message.raw_message.startswith("[语音:file:/tmp/voice.mp3]")
    assert "念这句话" in entry.message.raw_message
    assert entry.message.user_id == CHANNEL_ACCOUNT

    calls, results = _calls(_rebuilt(queue)), _results(_rebuilt(queue))
    assert calls[0]["name"] == "speak"
    assert json.loads(calls[0]["arguments"]) == {"text": "念这句话"}
    assert results[0]["file_index"].startswith("[语音:file:/tmp/voice.mp3]")


# ── send_long_reply ────────────────────────────────────────────────


async def test_send_long_reply_success_records_and_rebuilds(tmp_path, monkeypatch) -> None:
    """长回复成功：caption + Markdown 图片索引都写回，重建出 send_long_reply 调用。"""
    image = tmp_path / "markdown.png"
    image.write_bytes(b"png")
    queue = MessageQueue(bot_account=BOT_ACCOUNT)

    async def fake_send_image(*args, **kwargs):
        return {"status": "ok"}

    monkeypatch.setattr(agent_handlers, "send_image", fake_send_image)
    orch = _orchestrator(config=_config(BOT_ACCOUNT))

    await orch._agent_send_long_reply_handler(
        SimpleNamespace(reply_sent=False),
        _event(),
        queue,
        queue,
        GROUP_KEY,
        MessageNumbering(),
        image_path=str(image),
        caption="说明文字",
        markdown="# 标题内容",
    )
    await _drain(orch._sender)

    texts = [entry.message.raw_message for entry in _message_entries(queue)]
    assert texts[0] == "说明文字"
    assert texts[1].startswith("[Markdown图片:file:")
    assert "# 标题内容" in texts[1]

    calls = _calls(_rebuilt(queue))
    assert [call["name"] for call in calls] == ["send_long_reply", "send_long_reply"]
    arguments = [json.loads(call["arguments"]) for call in calls]
    assert arguments == [{"caption": "说明文字"}, {"image_path": str(image)}]


async def test_send_long_reply_failed_image_is_not_recorded(tmp_path, monkeypatch) -> None:
    image = tmp_path / "markdown.png"
    image.write_bytes(b"png")
    queue = MessageQueue(bot_account=BOT_ACCOUNT)

    async def failing_send_image(*args, **kwargs):
        return {"status": "failed", "message": "boom"}

    monkeypatch.setattr(agent_handlers, "send_image", failing_send_image)
    orch = _orchestrator(config=_config(BOT_ACCOUNT))

    await orch._agent_send_long_reply_handler(
        SimpleNamespace(reply_sent=False),
        _event(),
        queue,
        queue,
        GROUP_KEY,
        MessageNumbering(),
        image_path=str(image),
        caption="",
        markdown="# 标题内容",
    )
    await _drain(orch._sender)

    assert _message_entries(queue) == []


# ── send_official_markdown ─────────────────────────────────────────


async def test_send_official_markdown_payload_history_and_rebuild() -> None:
    """官方 Markdown：线上载荷是 official_markdown 段；历史写回文本并重建同名工具调用。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    adapter = _Adapter()
    orch = _orchestrator(adapter=adapter, config=_config(BOT_ACCOUNT))

    await orch._agent_send_official_markdown_handler(
        SimpleNamespace(reply_sent=False),
        _event(bot_account=CHANNEL_ACCOUNT),
        queue,
        queue,
        GROUP_KEY,
        MessageNumbering(),
        content="# 标题",
    )
    await _drain(orch._sender)

    payload, kwargs = adapter.calls[-1]
    assert payload == [{"type": "official_markdown", "data": {"content": "# 标题"}}]
    assert kwargs.get("channel") == "official"
    assert _message_entries(queue)[0].message.raw_message == "# 标题"
    assert _message_entries(queue)[0].message.user_id == CHANNEL_ACCOUNT

    call = _calls(_rebuilt(queue))[0]
    assert call["name"] == "send_official_markdown"
    assert json.loads(call["arguments"]) == {"content": "# 标题"}


# ── 后台通知 ───────────────────────────────────────────────────────


def test_background_notification_mirrors_into_next_transcript() -> None:
    """通知镜像写队列：下一轮重建 transcript 能看到 [通知:source]。"""
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._group_queue = MessageQueue(bot_account=BOT_ACCOUNT)
    orch._friend_queue = MessageQueue(bot_account=BOT_ACCOUNT)
    orch._logger = NullLogger()

    assert orch.record_notification(kind="group", conversation_id="77", source="drawing", content="画好了") is True
    assert build_role_messages(orch._group_queue, "77", bot_account=BOT_ACCOUNT) == [
        {"role": "user", "content": "[通知:drawing] 画好了"}
    ]


# ── 负 message_id / bot_account 识别 / 重置裁剪 ────────────────────


async def test_negative_synthetic_id_does_not_regress_last_reply_position() -> None:
    """自身发言的负 id 不能写成 last_reply_position（否则重置后新旧区段全乱）。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    queue.push(GROUP_KEY, _group_message(777, user_id=7, self_id=None, text="用户消息"))
    sender = _sender(config=_config(BOT_ACCOUNT))
    await sender.send_reply(
        _event(pre_reply_message_id=777),
        "自身回复",
        self_sent=SelfSentSink(queue=queue, snapshot=None, queue_key=GROUP_KEY),
    )
    await _drain(sender)

    before_message_id = queue.get_last_message_id(GROUP_KEY)
    assert before_message_id is not None and before_message_id < 0

    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = None
    orch._last_reply_time = {}
    orch._record_reply_delivered(
        _event(pre_reply_message_id=777), queue, GROUP_KEY, before_message_id=before_message_id
    )
    assert queue.get_last_reply_position(GROUP_KEY) == 777


async def test_self_sent_tool_call_rebuild_does_not_depend_on_account_context() -> None:
    """tool_call 元数据独立于账号集合：user_id=0（账号未解析）也能重建工具历史。"""
    queue = MessageQueue()
    sender = _sender(config=_config(0))

    await _send_text(sender, queue, "自身发言", bot_account=0)
    await _drain(sender)

    entry = _message_entries(queue)[0]
    assert entry.message.user_id == 0 and entry.tool_call is not None
    call = _calls(_rebuilt(queue, bot_account=0))[0]
    assert json.loads(call["arguments"]) == {"text": "自身发言"}


def test_soft_restart_replay_without_tool_metadata_rebuilds_plain_send_reply() -> None:
    """软重启从 DB 补齐的自身发言只有文本：tool 语义丢失，退化为 send_reply 文本。"""
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    restored_text = "[图片:tmp_abc123 file:/data/media/a.png]"
    queue.push_history(GROUP_KEY, _group_message(-99, user_id=BOT_ACCOUNT, self_id=BOT_ACCOUNT, text=restored_text))

    call = _calls(_rebuilt(queue))[0]
    assert call["name"] == "send_reply"
    assert json.loads(call["arguments"]) == {"text": restored_text}


async def test_numbering_should_not_expose_negative_msg_id_for_self_messages() -> None:
    queue = MessageQueue(bot_account=BOT_ACCOUNT)
    sender = _sender(config=_config(BOT_ACCOUNT))
    await _send_text(sender, queue, "自身发言")
    await _drain(sender)

    numbering = MessageNumbering(bot_account=BOT_ACCOUNT, queue=queue, queue_key=GROUP_KEY)
    assert "msg_id=-" not in numbering.apply(queue, GROUP_KEY)


async def test_queue_trim_leaves_consistent_synthetic_tool_pairs() -> None:
    """队列容量裁剪后重建历史仍成对（无孤立 tool 回执/悬空 tool_calls）。"""
    queue = MessageQueue(max_size=4, bot_account=BOT_ACCOUNT)
    sender = _sender(config=_config(BOT_ACCOUNT))
    for index in range(4):
        await _send_text(sender, queue, f"第{index}条" + "。" * 5)
    await _drain(sender)
    for index in range(6):
        queue.push(GROUP_KEY, _group_message(1000 + index, user_id=index + 1, self_id=None, text=f"u{index}"))

    rebuilt = _rebuilt(queue)
    call_ids = [call["id"] for call in rebuilt if call.get("tool_calls") for call in call["tool_calls"]]
    result_ids = [result["tool_call_id"] for result in rebuilt if result.get("role") == "tool"]
    assert call_ids == result_ids
