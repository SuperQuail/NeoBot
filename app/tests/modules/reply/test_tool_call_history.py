"""工具调用历史：记录全部工具，发送工具 full、非发送工具 compact。

修复前：只有发送类工具会把产物写回队列（send_reply 图片/文字、speak、
send_long_reply、send_official_markdown），其它工具（联网搜索、读文件、技能加载…）
执行完就丢；管线重置后模型看不到「刚才调过什么」，容易重复调用同样的工具。
现在：非发送工具低权重入队为 QueueEntryType.TOOL_CALL（完整 args/result 保留在
条目与存储里），聊天管线只 compact 回放「工具名 + 成败」；发送工具维持 full 显示。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_contracts.ports.logging import NullLogger
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory

from neobot_app.bot_accounts import bind_bot_accounts
from neobot_app.config.schemas.bot import Bot, BotConfig
from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue, QueueEntryType, SelfSentToolCall
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.sender import ReplySender, SelfSentSink

GROUP_KEY = "42"
BOT_QQ = 10001
_SECRET = "内部机密查询内容"
_SECRET_RESULT = "机密结果正文"


# ── 假件 ────────────────────────────────────────────────────────────


class _FakeUow:
    def __init__(self) -> None:
        self.saved: list[IncomingMessage] = []
        self.messages = SimpleNamespace(save_message=self._save)
        self.commit = AsyncMock()

    async def _save(self, message: IncomingMessage) -> None:
        self.saved.append(message)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _UowFactory:
    def __init__(self) -> None:
        self.uows: list[_FakeUow] = []

    def __call__(self) -> _FakeUow:
        uow = _FakeUow()
        self.uows.append(uow)
        return uow


class _CapturingSender:
    """记录「哪些工具调用被排入落盘」的假 sender。"""

    def __init__(self) -> None:
        self.tool_calls: list[tuple[ConversationRef, SelfSentToolCall]] = []

    def schedule_persist_tool_call(self, conv_ref, record, *, occurred_at=None, bot_account=0):
        self.tool_calls.append((conv_ref, record))
        return None


class _Executor:
    def __init__(self, *, result=None, error: Exception | None = None, delay: float = 0.0) -> None:
        self.result = result
        self.error = error
        self.delay = delay
        self.executed: list[tuple[str, dict]] = []

    def is_tool_authorized(self, name: str) -> bool:
        return True

    def authorization_error(self, name: str) -> str:
        return f"工具 {name} 未授权"

    async def execute(self, name: str, args: dict):
        self.executed.append((name, args))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


class _Toolset:
    def __init__(self, executor: _Executor) -> None:
        self.executor = executor


def _config() -> BotConfig:
    config = BotConfig()
    config.bot = Bot(account=BOT_QQ)
    return config


def _event() -> ReplyEvent:
    event = ReplyEvent(
        mode="agent",
        conversation_ref=ConversationRef(kind="group", id=GROUP_KEY),
        bot_account=BOT_QQ,
    )
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _orchestrator(*, executor: _Executor | None = None) -> tuple[ReplyOrchestrator, _CapturingSender]:
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._logger = NullLogger()
    orch._config = _config()
    orch._provider = SimpleNamespace(native_vision=False)
    sender = _CapturingSender()
    orch._sender = sender
    orch._record_debug = lambda *args, **kwargs: None
    orch._get_max_wait_seconds = lambda: 1
    orch._get_model_response_timeout_seconds = lambda event: 5.0
    orch._get_dependency_timeout_seconds = lambda: 0.5
    orch._tool_failure_key = lambda name, args: f"{name}:{sorted(args)}"
    orch._tool_repeat_failure_hint = lambda name, failures: "重复失败提示"

    async def _emit(stage, event, **payload):
        return SimpleNamespace(consumed=False, payload={}, result=None)

    orch._emit_runtime_event = _emit
    return orch, sender


def _tool_call(name: str, arguments: dict, *, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def _tool_entries(queue: MessageQueue) -> list:
    return [entry for entry in queue.entries(GROUP_KEY) if entry.kind == QueueEntryType.TOOL_CALL]


def _rebuilt(queue: MessageQueue, *, bot_account: int = BOT_QQ) -> list[dict]:
    return build_role_messages(queue, GROUP_KEY, bot_account=bot_account)


def _calls(messages: list[dict]) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for message in messages:
        if not message.get("tool_calls"):
            continue
        function = message["tool_calls"][0]["function"]
        calls.append((function["name"], function["arguments"]))
    return calls


def _tool_results(messages: list[dict]) -> list[dict]:
    return [json.loads(message["content"]) for message in messages if message.get("role") == "tool"]


@pytest.fixture(autouse=True)
def _reset_bot_accounts():
    bind_bot_accounts(None, None)
    yield
    bind_bot_accounts(None, None)


async def _run_tool(
    name: str,
    arguments: dict,
    *,
    call_id: str = "call_1",
    executor: _Executor | None = None,
) -> tuple[MessageQueue, MessageQueue, ReplyOrchestrator, _CapturingSender]:
    orch, sender = _orchestrator(executor=executor)
    queue = MessageQueue(bot_account=BOT_QQ)
    queue_copy = queue.clone(GROUP_KEY)
    await orch._agent_execute_tool_calls(
        event=_event(),
        queue=queue,
        queue_copy=queue_copy,
        queue_key=GROUP_KEY,
        iteration=0,
        tool_calls=[_tool_call(name, arguments, call_id=call_id)],
        messages=[],
        reply_toolset=_Toolset(executor or _Executor(result="ok")),
        tool_name_by_call_id={},
        tool_failure_streak={},
        silent_remaining=lambda: None,
        reset_silent_deadline=lambda extra: None,
    )
    return queue, queue_copy, orch, sender


# ── 非发送工具：成功/失败/超时 compact 入队 ────────────────────────


async def test_non_send_tool_success_is_recorded_compact() -> None:
    queue, queue_copy, _orch, sender = await _run_tool(
        "web_search", {"query": _SECRET}, executor=_Executor(result={"page": _SECRET_RESULT})
    )

    entries = _tool_entries(queue)
    assert len(entries) == 1
    record = entries[0].tool_call
    assert record.name == "web_search"
    assert record.ok is True
    assert record.compact is True
    assert record.call_id == "call_1"
    # 完整参数/结果保留在条目里（调试/存储用）
    assert record.arguments == {"query": _SECRET}
    assert _SECRET_RESULT in str(record.result)
    assert entries[0].weight < 1.0
    # 同一管线的快照也同步入队：不会被 diff 当新消息重复注入
    assert len(_tool_entries(queue_copy)) == 1
    # 已异步排入落库
    assert [record.name for _, record in sender.tool_calls] == ["web_search"]


async def test_non_send_tool_failure_is_recorded_without_leaking_content() -> None:
    queue, _queue_copy, _orch, _sender = await _run_tool(
        "web_search", {"query": _SECRET}, executor=_Executor(error=RuntimeError(_SECRET_RESULT))
    )

    record = _tool_entries(queue)[0].tool_call
    assert record.ok is False
    assert record.compact is True
    # 完整失败信息仍保留在数据里，供调试面板/存储查看
    assert _SECRET_RESULT in str(record.result)

    messages = _rebuilt(queue)
    assert _calls(messages) == [("web_search", "{}")]
    assert _tool_results(messages) == [{"ok": False}]
    rendered = json.dumps(messages, ensure_ascii=False)
    assert _SECRET not in rendered and _SECRET_RESULT not in rendered


async def test_non_send_tool_timeout_is_recorded_as_failure() -> None:
    orch, _sender = _orchestrator(executor=_Executor(delay=5.0))
    orch._get_model_response_timeout_seconds = lambda event: 0.01
    orch._get_dependency_timeout_seconds = lambda: 0.01
    queue = MessageQueue(bot_account=BOT_QQ)

    await orch._agent_execute_tool_calls(
        event=_event(),
        queue=queue,
        queue_copy=queue.clone(GROUP_KEY),
        queue_key=GROUP_KEY,
        iteration=0,
        tool_calls=[_tool_call("web_search", {"query": "x"})],
        messages=[],
        reply_toolset=_Toolset(_Executor(delay=5.0)),
        tool_name_by_call_id={},
        tool_failure_streak={},
        silent_remaining=lambda: None,
        reset_silent_deadline=lambda extra: None,
    )

    record = _tool_entries(queue)[0].tool_call
    assert record.ok is False
    assert "超时" in str(record.result)


async def test_send_tools_are_not_recorded_twice() -> None:
    """发送工具已有 full self-sent 记录，tool exec 不得再写 compact 条目。"""
    for name in ("send_reply", "speak", "send_long_reply", "send_official_markdown"):
        queue, _copy, _orch, _sender = await _run_tool(name, {"text": "x"})
        assert _tool_entries(queue) == [], name


# ── 重建：compact assistant.tool_calls + tool 回执 ────────────────


def test_tool_call_entry_rebuilds_compact_history() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    queue.push_tool_call(
        GROUP_KEY,
        SelfSentToolCall(
            name="web_search",
            arguments={"query": _SECRET},
            result={"ok": True, "value": _SECRET_RESULT},
            ok=True,
            compact=True,
            call_id="call_9",
        ),
    )

    messages = _rebuilt(queue)
    assert _calls(messages) == [("web_search", "{}")]
    assert _tool_results(messages) == [{"ok": True}]
    assert messages[0]["tool_calls"][0]["id"] == messages[1]["tool_call_id"] == "call_9"
    rendered = json.dumps(messages, ensure_ascii=False)
    assert _SECRET not in rendered and _SECRET_RESULT not in rendered


# ── 纯文本渲染：队列 to_text / diff / numbering ────────────────────


def _push_tool(queue: MessageQueue, *, ok: bool = True, call_id: str = "call_9") -> None:
    queue.push_tool_call(
        GROUP_KEY,
        SelfSentToolCall(
            name="web_search",
            arguments={"query": _SECRET},
            result={"ok": ok, "value": _SECRET_RESULT},
            ok=ok,
            compact=True,
            call_id=call_id,
        ),
    )


def test_queue_text_renders_compact_tool_line() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    _push_tool(queue)

    text = queue.to_text(GROUP_KEY)
    assert "[工具调用] web_search 成功" in text
    assert _SECRET not in text and _SECRET_RESULT not in text


def test_queue_diff_renders_compact_tool_line() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    previous = queue.clone(GROUP_KEY)
    _push_tool(queue, ok=False)

    diff_text = queue.diff_to_text(previous, GROUP_KEY)
    assert "[工具调用] web_search 失败" in diff_text
    assert _SECRET not in diff_text and _SECRET_RESULT not in diff_text


def test_numbering_renders_compact_tool_line() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    _push_tool(queue)
    numbering = MessageNumbering(bot_account=BOT_QQ)

    text = numbering.apply(queue, GROUP_KEY)

    assert "[工具调用] web_search 成功" in text
    assert _SECRET not in text and _SECRET_RESULT not in text


def test_numbering_apply_new_renders_compact_tool_line() -> None:
    queue = MessageQueue(bot_account=BOT_QQ)
    numbering = MessageNumbering(bot_account=BOT_QQ)
    entry = SimpleNamespace(
        kind=QueueEntryType.TOOL_CALL,
        message=None,
        notice=None,
        replied_messages=[],
        notification=None,
        reaction=None,
        poke=None,
        occurred_at=None,
        tool_call=SelfSentToolCall(
            name="read_file",
            arguments={"path": _SECRET},
            result={"ok": False, "error": _SECRET_RESULT},
            ok=False,
            compact=True,
            call_id="call_10",
        ),
    )

    text = numbering.apply_new([entry], queue)

    assert "[工具调用] read_file 失败" in text
    assert _SECRET not in text and _SECRET_RESULT not in text


# ── 队列裁剪：工具上下文与聊天记录同生共死 ────────────────────────


def test_queue_trim_keeps_tool_history_paired() -> None:
    queue = MessageQueue(max_size=3, bot_account=BOT_QQ)
    from neobot_adapter.model.message import GroupMessage, MessageSegment

    def _user(index: int):
        return GroupMessage(
            message_id=index,
            user_id=1000 + index,
            group_id=int(GROUP_KEY),
            message=[MessageSegment(type="text", data={"text": f"消息{index}"})],
            raw_message=f"消息{index}",
        )

    for index in range(5):
        queue.push(GROUP_KEY, _user(index))
        _push_tool(queue, call_id=f"call_{index}")

    retained = _tool_entries(queue)
    messages = _rebuilt(queue)
    assistant_ids = [message["tool_calls"][0]["id"] for message in messages if message.get("tool_calls")]
    tool_ids = [message["tool_call_id"] for message in messages if message.get("role") == "tool"]
    # 每条保留的工具调用都有配对回执，数量与队列里保留的条目一致
    assert assistant_ids == tool_ids
    assert len(assistant_ids) == len(retained)
    assert len(assistant_ids) < 5  # 确实发生了裁剪


# ── 发送工具 full 不回归 ──────────────────────────────────────────


async def test_send_reply_image_keeps_full_history(tmp_path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"png")

    async def registrar(path):
        return SimpleNamespace(image_id="tmp_abc")

    sender = ReplySender(
        adapter=SimpleNamespace(send=AsyncMock(return_value={"status": "ok", "message_id": 1})),
        file_server=SimpleNamespace(_enabled=False, register_file=lambda p: f"file:///{p}"),
        config=_config(),
        bot_name="Bot",
        emoji_service=SimpleNamespace(
            get_entry=lambda number: SimpleNamespace(file_path=image),
            record_usage=AsyncMock(),
        ),
        image_registrar=registrar,
        self_sent_uow_factory=_UowFactory(),
        logger=NullLogger(),
    )
    queue = MessageQueue(bot_account=BOT_QQ)
    event = _event()

    await sender.send_reply(event, "", images=[1], self_sent=SelfSentSink(queue, None, GROUP_KEY))

    entry = queue.entries(GROUP_KEY)[-1]
    assert entry.kind == QueueEntryType.MESSAGE
    assert entry.tool_call.compact is False
    messages = _rebuilt(queue)
    assert _calls(messages) == [("send_reply", json.dumps({"emoji_numbers": [1]}))]


# ── 持久化契约：IncomingMessage.tool_call ────────────────────────


def _make_sender(uow_factory) -> ReplySender:
    return ReplySender(
        adapter=None,
        file_server=None,
        config=_config(),
        bot_name="Bot",
        self_sent_uow_factory=uow_factory,
        logger=NullLogger(),
    )


async def test_persist_self_sent_message_writes_tool_call() -> None:
    factory = _UowFactory()
    sender = _make_sender(factory)
    record = SelfSentToolCall(
        name="send_reply",
        arguments={"emoji_numbers": [1]},
        result={"ok": True, "image_index": "[图片:tmp_abc file:a.png]"},
        ok=True,
        compact=False,
        call_id="call_img",
    )

    await sender.persist_self_sent_message(
        ConversationRef(kind="group", id=GROUP_KEY), "[图片:tmp_abc file:a.png]", tool_call=record
    )

    saved = factory.uows[0].saved[0]
    assert saved.text == "[图片:tmp_abc file:a.png]"
    assert saved.tool_call["name"] == "send_reply"
    assert saved.tool_call["compact"] is False
    assert saved.tool_call["arguments"] == {"emoji_numbers": [1]}


async def test_persist_tool_call_writes_empty_text_and_tool_call() -> None:
    factory = _UowFactory()
    sender = _make_sender(factory)
    record = SelfSentToolCall(
        name="web_search",
        arguments={"query": _SECRET},
        result={"ok": False, "error": _SECRET_RESULT},
        ok=False,
        compact=True,
        call_id="call_search",
    )

    await sender.persist_tool_call(ConversationRef(kind="group", id=GROUP_KEY), record)

    saved = factory.uows[0].saved[0]
    assert saved.text == ""
    assert saved.event_id.startswith("tool:call_search:")
    assert saved.tool_call["name"] == "web_search"
    assert saved.tool_call["compact"] is True
    assert saved.tool_call["ok"] is False


@pytest_asyncio.fixture
async def uow_factory(tmp_path):
    """每用例独立的临时 sqlite UoW 工厂（与生产同一套存储实现）。"""
    engine = create_engine(sqlite_url(tmp_path / "tool_history.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_uow_factory(engine)
    await engine.dispose()


async def test_tool_call_roundtrips_through_storage(uow_factory) -> None:
    """落库 → 读回：tool_call 完整往返（storage 不透明 JSON）。"""
    sender = _make_sender(uow_factory)
    conv = ConversationRef(kind="group", id=GROUP_KEY)
    searched = SelfSentToolCall(
        name="web_search",
        arguments={"query": _SECRET},
        result={"ok": True, "value": _SECRET_RESULT},
        ok=True,
        compact=True,
        call_id="call_rt",
    )
    image = SelfSentToolCall(
        name="send_reply",
        arguments={"emoji_numbers": [1]},
        result={"ok": True, "image_index": "[图片:tmp_abc file:a.png]"},
        ok=True,
        compact=False,
        call_id="call_img",
    )

    await sender.persist_tool_call(conv, searched)
    await sender.persist_self_sent_message(conv, "[图片:tmp_abc file:a.png]", tool_call=image)

    async with uow_factory() as uow:
        history = await uow.messages.get_history(conv, limit=10)

    stored_tool = next(
        message for message in history if message.event_id.startswith("tool:call_rt:")
    )
    assert stored_tool.text == ""
    assert stored_tool.tool_call == {
        "name": "web_search",
        "arguments": {"query": _SECRET},
        "result": {"ok": True, "value": _SECRET_RESULT},
        "ok": True,
        "compact": True,
        "call_id": "call_rt",
    }
    stored_image = next(message for message in history if message.text.startswith("[图片:"))
    assert stored_image.tool_call["name"] == "send_reply"
    assert stored_image.tool_call["compact"] is False
    assert stored_image.tool_call["arguments"] == {"emoji_numbers": [1]}


async def test_persist_tool_call_swallows_store_errors() -> None:
    def exploding_factory():
        raise RuntimeError("数据库不可用")

    sender = _make_sender(exploding_factory)

    # 不抛异常即为通过
    await sender.persist_tool_call(
        ConversationRef(kind="group", id=GROUP_KEY),
        SelfSentToolCall(name="web_search", compact=True, call_id="call_x"),
    )


async def test_tool_result_error_string_is_marked_failed() -> None:
    """工具层用「错误：…」返回失败时，compact 历史必须标失败且不暴露文本。"""
    queue, _copy, _orch, _sender = await _run_tool(
        "read_file",
        {"path": _SECRET},
        executor=_Executor(result=f"错误：{_SECRET_RESULT}"),
    )

    record = _tool_entries(queue)[0].tool_call
    assert record.ok is False

    messages = _rebuilt(queue)
    tool_results = _tool_results(messages)
    assert tool_results == [{"ok": False}]
    assert _SECRET_RESULT not in json.dumps(messages, ensure_ascii=False)


async def test_failed_send_tool_is_recorded_compact() -> None:
    """发送工具失败时没有 full self-sent 记录，补一条 compact 失败历史。"""
    queue, _copy, _orch, _sender = await _run_tool(
        "send_reply",
        {"text": _SECRET},
        executor=_Executor(result=False),
    )

    entries = _tool_entries(queue)
    assert len(entries) == 1
    assert entries[0].tool_call.name == "send_reply"
    assert entries[0].tool_call.ok is False
    assert entries[0].tool_call.compact is True

    tool_results = _tool_results(_rebuilt(queue))
    assert tool_results == [{"ok": False}]
    assert _SECRET not in json.dumps(_rebuilt(queue), ensure_ascii=False)
