"""self-sent 工具调用历史：发送成功后写回队列，管线重置后可重建为真实工具调用。

修复前根因（复现锁定）：发送层只把每次真实发送写成一条纯文本 self-sent 队列
消息（图片是 "[图片:tmp_x file:...]"、语音是 "[语音:...]"、长回复是
"[Markdown图片:...]"），role_messages 把所有 assistant 正文统一改写成
send_reply({"text": ...}) —— 重置后的历史里看不到 emoji_numbers/images 参数，
也看不到 speak / send_long_reply / send_official_markdown 的工具名；再加上
self-sent 消息没有 self_id、账号集合对不上时会被判成 user 消息。模型因此看不出
「自己已经发过图/语音」，会反复重发。

修复后：发送层在队列条目上记录 tool_call(name/arguments/result)，role_messages
优先据此重建 assistant.tool_calls + tool 成功回执；元数据随条目一起进出队列，
所以重置时只丢「早于最早保留聊天记录」的工具上下文。
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
from neobot_app.message.queue import MessageQueue, SelfSentToolCall
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.sender import ReplySender, SelfSentSink

GROUP_KEY = "42"
BOT_QQ = 10001


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
    def __init__(self, paths: dict[int, Path] | None = None) -> None:
        self.paths = paths or {}
        self.used: list[int] = []

    def get_entry(self, number: int):
        path = self.paths.get(number)
        return SimpleNamespace(file_path=path) if path is not None else None

    async def record_usage(self, number: int) -> None:
        self.used.append(number)


class _FakeUow:
    def __init__(self) -> None:
        self.messages = SimpleNamespace(save_message=AsyncMock())
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _config(account: int = BOT_QQ) -> BotConfig:
    config = BotConfig()
    config.bot = Bot(account=account)
    return config


def _sender(
    *,
    config=None,
    adapter=None,
    emoji=None,
    registrar=None,
) -> ReplySender:
    return ReplySender(
        adapter=adapter or _Adapter(),
        file_server=_FileServer(),
        config=config if config is not None else _config(),
        bot_name="Bot",
        emoji_service=emoji,
        image_registrar=registrar,
        self_sent_uow_factory=_FakeUow,
        logger=NullLogger(),
    )


def _event(*, bot_account: int = BOT_QQ) -> ReplyEvent:
    event = ReplyEvent(
        mode="agent",
        conversation_ref=ConversationRef(kind="group", id=GROUP_KEY),
        bot_account=bot_account,
    )
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _user_message(user_id: int, text: str):
    from neobot_adapter.model.message import GroupMessage, MessageSegment

    return GroupMessage(
        message_id=user_id,
        user_id=user_id,
        group_id=int(GROUP_KEY),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def _sink(queue: MessageQueue) -> SelfSentSink:
    return SelfSentSink(queue=queue, snapshot=None, queue_key=GROUP_KEY)


def _entries(queue: MessageQueue) -> list:
    return [entry for entry in queue.entries(GROUP_KEY) if entry.kind.value == "message"]


def _rebuilt(queue: MessageQueue, *, bot_account: int = BOT_QQ) -> list[dict]:
    return build_role_messages(queue, GROUP_KEY, bot_account=bot_account)


def _calls(messages: list[dict]) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []
    for message in messages:
        if not message.get("tool_calls"):
            continue
        function = message["tool_calls"][0]["function"]
        calls.append((function["name"], json.loads(function["arguments"])))
    return calls


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


@pytest.fixture(autouse=True)
def _reset_bot_accounts():
    bind_bot_accounts(None, None)
    yield
    bind_bot_accounts(None, None)


# ── 队列元数据 ─────────────────────────────────────────────────────


def test_queue_entry_carries_tool_call_and_clone_keeps_it() -> None:
    """工具元数据挂在队列条目上，克隆（管线快照）后仍在。"""
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push(
        GROUP_KEY,
        _sender()._build_self_sent_message(ConversationRef(kind="group", id=GROUP_KEY), "在的", -1, bot_account=BOT_QQ),
        tool_call=SelfSentToolCall(name="send_reply", arguments={"text": "在的"}, result={"ok": True}),
    )

    entry = _entries(queue)[0]
    assert entry.tool_call is not None
    assert entry.tool_call.name == "send_reply"
    cloned = _entries(queue.clone(GROUP_KEY))[0]
    assert cloned.tool_call.arguments == {"text": "在的"}


# ── send_reply：文字 ───────────────────────────────────────────────


async def test_send_reply_text_rebuilds_send_reply_tool_call() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    sender = _sender()

    assert await sender.send_reply(_event(), "在的", self_sent=_sink(queue)) is True
    await _drain(sender)

    assert _calls(_rebuilt(queue)) == [("send_reply", {"text": "在的"})]
    result = _results(_rebuilt(queue))[0]
    assert result["ok"] is True
    # assistant.tool_calls 与 tool 回执必须配对
    assistant = next(m for m in _rebuilt(queue) if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["id"] == result["tool_call_id"]


# ── send_reply：图片（单独 / 图片+文字） ───────────────────────────


async def test_send_reply_image_only_rebuilds_emoji_call_and_index(tmp_path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"png")

    async def registrar(path):
        return SimpleNamespace(image_id="tmp_abc")

    queue = MessageQueue(bot_account=BOT_QQ)
    sender = _sender(emoji=_EmojiService({1: image}), registrar=registrar)

    assert await sender.send_reply(_event(), "", images=[1], self_sent=_sink(queue)) is True
    await _drain(sender)

    entry = _entries(queue)[0]
    # 队列里仍是可理解的文本索引（其它渲染路径依赖它）
    assert entry.message.raw_message.startswith("[图片:tmp_abc file:")
    # 重建后是 send_reply(emoji_numbers=[1])，不是一段 "[图片:...]" 正文
    assert _calls(_rebuilt(queue)) == [("send_reply", {"emoji_numbers": [1]})]
    result = _results(_rebuilt(queue))[0]
    assert result["image_index"] == entry.message.raw_message
    # 角色必须是 assistant：账号集合为空也不能变成 user 消息
    assert [m["role"] for m in _rebuilt(queue) if m["role"] != "user"] == ["assistant", "tool"]


async def test_send_reply_image_plus_text_rebuilds_two_tool_calls(tmp_path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"png")

    queue = MessageQueue(bot_account=BOT_QQ)
    sender = _sender(emoji=_EmojiService({1: image}))

    await sender.send_reply(_event(), "看图", images=[1], self_sent=_sink(queue))
    await _drain(sender)

    assert _calls(_rebuilt(queue)) == [
        ("send_reply", {"emoji_numbers": [1]}),
        ("send_reply", {"text": "看图"}),
    ]
    assert len(_results(_rebuilt(queue))) == 2


async def test_self_sent_message_sets_self_id_and_survives_unknown_account(tmp_path) -> None:
    """账号未解析（user_id=0/账号集合为空）时，self_id 或工具元数据仍能认出是自己。"""
    queue = MessageQueue()  # 不登记任何 bot 账号
    sender = _sender(config=_config(0))

    await sender.send_reply(_event(bot_account=0), "在的", self_sent=_sink(queue))
    await _drain(sender)

    entry = _entries(queue)[0]
    assert entry.tool_call is not None
    assert entry.message.self_id == entry.message.user_id == 0
    # 重建结果不依赖账号集合：仍是 assistant 工具调用
    assert _calls(_rebuilt(queue, bot_account=0)) == [("send_reply", {"text": "在的"})]

    # 正常账号下 self_id 与 user_id 同值，历史回放可自证「是我发的」
    queue2 = MessageQueue()
    sender2 = _sender()
    await sender2.send_reply(_event(), "在的", self_sent=SelfSentSink(queue=queue2, snapshot=None, queue_key=GROUP_KEY))
    await _drain(sender2)
    assert _entries(queue2)[0].message.self_id == BOT_QQ


# ── 类似工具：speak / send_long_reply / send_official_markdown ─────


class _TtsService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize_segment(self, text: str):
        self.calls.append(text)
        return {"type": "record", "data": {"file": "voice.amr"}}


def _orchestrator(*, adapter=None, config=None, tts_service=None) -> ReplyOrchestrator:
    """只装配 agent 工具 handler 依赖的编排器（不跑真实循环）。"""
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._adapter = adapter or _Adapter()
    orch._file_server = _FileServer()
    orch._config = config if config is not None else _config()
    orch._logger = NullLogger()
    orch._sender = _sender(config=orch._config, adapter=orch._adapter)
    orch._last_reply_time = {}
    orch._tts_service = tts_service
    orch._clear_unsent_marker = lambda event: None
    orch._record_reply_delivered = lambda *args, **kwargs: None
    return orch


async def test_speak_history_rebuilds_speak_tool_call() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    tts = _TtsService()
    orch = _orchestrator(tts_service=tts)

    await orch._agent_speak_handler(
        SimpleNamespace(reply_sent=False),
        _event(),
        queue,
        queue,
        GROUP_KEY,
        "你好呀",
    )
    await _drain(orch._sender)

    assert tts.calls == ["你好呀"]
    assert _calls(_rebuilt(queue)) == [("speak", {"text": "你好呀"})]
    result = _results(_rebuilt(queue))[0]
    assert "语音" in result["file_index"]


async def test_send_long_reply_rebuilds_send_long_reply_tool_calls(tmp_path) -> None:
    image = tmp_path / "markdown.png"
    image.write_bytes(b"png")
    queue = MessageQueue(bot_account=BOT_QQ)
    orch = _orchestrator()

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

    assert _calls(_rebuilt(queue)) == [
        ("send_long_reply", {"caption": "说明文字"}),
        ("send_long_reply", {"image_path": str(image)}),
    ]
    result = _results(_rebuilt(queue))[1]
    assert result["image_index"].startswith("[Markdown图片:")


async def test_send_long_reply_failed_image_is_not_written_to_history(tmp_path, monkeypatch) -> None:
    """发送失败只记日志：不得写回「已发送」历史（否则重置后历史谎报成功）。"""
    image = tmp_path / "markdown.png"
    image.write_bytes(b"png")
    queue = MessageQueue(bot_account=BOT_QQ)

    async def failing_send_image(*args, **kwargs):
        return {"status": "failed", "message": "boom"}

    monkeypatch.setattr(agent_handlers, "send_image", failing_send_image)
    orch = _orchestrator()

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

    assert _entries(queue) == []


async def test_send_official_markdown_rebuilds_official_tool_call() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    adapter = _Adapter()
    orch = _orchestrator(adapter=adapter)

    await orch._agent_send_official_markdown_handler(
        SimpleNamespace(reply_sent=False),
        _event(bot_account=BOT_QQ),
        queue,
        queue,
        GROUP_KEY,
        MessageNumbering(),
        content="# 标题",
    )
    await _drain(orch._sender)

    assert adapter.calls[-1][1].get("channel") == "official"
    assert _calls(_rebuilt(queue)) == [("send_official_markdown", {"content": "# 标题"})]
    # 账号集合对不上时也不能把官方卡片记成 user 消息
    assert all(m["role"] != "user" or "标题" not in str(m.get("content") or "") for m in _rebuilt(queue))


# ── 重置裁剪：工具上下文与聊天记录同生共死 ─────────────────────────


async def test_queue_trim_drops_tool_context_with_chat_record(tmp_path) -> None:
    """队列裁剪后重建仍是成对的 assistant.tool_calls + tool 回执，无孤儿。"""
    image = tmp_path / "a.png"
    image.write_bytes(b"png")
    queue = MessageQueue(max_size=6, bot_account=BOT_QQ)
    sender = _sender(emoji=_EmojiService({1: image}))

    for index in range(6):
        queue.push(GROUP_KEY, _user_message(1000 + index, f"用户{index}"))
        await sender.send_reply(_event(), f"回复{index}", images=[1], self_sent=_sink(queue))
    await _drain(sender)

    retained_tool_entries = [entry for entry in _entries(queue) if entry.tool_call is not None]
    messages = _rebuilt(queue)
    call_ids = [message["tool_calls"][0]["id"] for message in messages if message.get("tool_calls")]
    result_ids = [message["tool_call_id"] for message in messages if message.get("role") == "tool"]
    # 每个 assistant.tool_calls 都有回执，且数量与队列里保留下来的工具条目一致
    assert call_ids == result_ids
    assert len(call_ids) == len(retained_tool_entries)


async def test_failed_send_reply_is_not_written_to_history() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    sender = _sender(adapter=_Adapter(result={"status": "failed", "message": "boom"}))

    assert await sender.send_reply(_event(), "在的", self_sent=_sink(queue)) is False
    await _drain(sender)

    assert _entries(queue) == []
