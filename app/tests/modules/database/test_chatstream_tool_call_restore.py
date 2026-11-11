"""ChatStream 启动恢复：发送工具 full + 非发送工具 compact（软重启）。

工具调用历史落盘后，软重启时本地记录必须能还原成 role_messages 里的工具调用：
- 发送工具（send_reply 图片/文字等）带正文与完整 tool_call，恢复为 full 历史；
- 非发送工具（web_search 等）没有正文，恢复为 compact（只留工具名 + 成败）；
- 空 text 工具记录不能变成空白用户/assistant 消息，也不能被去重逻辑吞掉；
- 与后端历史按 occurred_at 合并顺序稳定，队列裁剪后 tool_call/回执仍成对。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

from neobot_adapter.model.response import (
    GetHistoryMsgListData,
    GetHistoryMsgListResponse,
    GetSignalMsgData,
    GroupData,
)
from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory

from neobot_app.bot_accounts import bind_bot_accounts
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.sender import ReplySender, SelfSentSink

GROUP_ID = 888888
GROUP_KEY = str(GROUP_ID)
BOT_QQ = 10001
USER_QQ = 20001
_NO_TIMESTAMP_INTERVAL = 10_000_000
_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_FULL_SEND_TOOL = {
    "name": "send_reply",
    "arguments": {"emoji_numbers": [1]},
    "result": {"ok": True, "image_index": "[图片:tmp_abc file:/x.png]"},
    "ok": True,
    "compact": False,
    "call_id": "call-image",
}
_SECRET_ARG = "内部机密查询内容"
_SECRET_RESULT = "机密结果正文"
_COMPACT_SUCCESS = {
    "name": "web_search",
    "arguments": {"q": _SECRET_ARG},
    "result": {"ok": True, "value": _SECRET_RESULT},
    "ok": True,
    "compact": True,
    "call_id": "call-search-ok",
}
_COMPACT_FAILURE = {
    "name": "web_search",
    "arguments": {"q": _SECRET_ARG},
    "result": {"ok": False, "error": _SECRET_RESULT},
    "ok": False,
    "compact": True,
    "call_id": "call-search-fail",
}


def _at(offset_seconds: int) -> datetime:
    return _BASE + timedelta(seconds=offset_seconds)


def _epoch(offset_seconds: int) -> int:
    return int(_at(offset_seconds).timestamp())


@pytest.fixture(autouse=True)
def _reset_bot_accounts_provider():
    bind_bot_accounts(
        SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ)),
        SimpleNamespace(accounts={"onebot": BOT_QQ}, profile=SimpleNamespace(account=BOT_QQ)),
    )
    yield
    bind_bot_accounts(None, None)


@pytest_asyncio.fixture
async def uow_factory(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "chatstream-tools.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_uow_factory(engine)
    await engine.dispose()


class _FakeAdapter:
    """只回答群历史查询的假适配器（官方/OneBot 形状）。"""

    def __init__(self, history: list | None = None) -> None:
        self.history = list(history or [])

    async def get_group_msg_history(self, group_id, count=20, reverse_order=False):
        return GetHistoryMsgListResponse(
            status="ok",
            retcode=0,
            data=GetHistoryMsgListData(messages=list(self.history)),
        )


def _backend_message(message_id: int, user_id: int, text: str, time_: int):
    return GetSignalMsgData(
        message_id=message_id,
        user_id=user_id,
        group_id=GROUP_ID,
        time=time_,
        raw_message=text,
        message=[{"type": "text", "data": {"text": text}}],
        sender={"user_id": user_id, "nickname": f"U{user_id}"},
    )


def _make_manager(adapter, uow_factory, *, max_size: int = 50):
    group_queue = MessageQueue(
        max_size=max_size,
        timestamp_interval_seconds=_NO_TIMESTAMP_INTERVAL,
        bot_account=BOT_QQ,
    )
    friend_queue = MessageQueue(
        max_size=max_size,
        timestamp_interval_seconds=_NO_TIMESTAMP_INTERVAL,
        bot_account=BOT_QQ,
    )
    manager = ChatStreamManager(
        adapter=adapter,
        uow_factory=uow_factory,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
    )
    return manager, group_queue


async def _save(
    uow_factory,
    *,
    event_id: str,
    text: str,
    occurred_at: datetime,
    tool_call: dict | None = None,
) -> None:
    async with uow_factory() as uow:
        await uow.messages.save_message(
            IncomingMessage(
                event_id=event_id,
                conversation=ConversationRef(kind="group", id=GROUP_KEY),
                sender_id=str(BOT_QQ),
                sender_name="测试机器人",
                text=text,
                occurred_at=occurred_at,
                tool_call=tool_call,
            )
        )
        await uow.commit()


def _roles(queue: MessageQueue) -> list[str]:
    return [item["role"] for item in _rebuilt(queue)]


def _rebuilt(queue: MessageQueue) -> list[dict]:
    return build_role_messages(queue, GROUP_KEY, bot_account=BOT_QQ)


def _calls(messages: list[dict]) -> list[dict]:
    return [
        message["tool_calls"][0]
        for message in messages
        if message.get("role") == "assistant" and message.get("tool_calls")
    ]


def _results(messages: list[dict]) -> list[dict]:
    return [message for message in messages if message.get("role") == "tool"]


def _texts(queue: MessageQueue) -> list[str]:
    return [message.raw_message for message in queue.iterate_from_oldest(GROUP_KEY)]


async def _drain(sender: ReplySender) -> None:
    tasks = list(sender._self_sent_persist_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _restore(uow_factory, history: list | None = None, *, max_size: int = 50):
    manager, queue = _make_manager(_FakeAdapter(history), uow_factory, max_size=max_size)
    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=30)
    return queue


async def test_load_recent_self_messages_returns_tool_call_records(uow_factory):
    """启动补齐读取的本地记录要带回 tool_call，且能区分 tool: 工具行。"""
    await _save(
        uow_factory,
        event_id="self:-401",
        text="[图片:tmp_abc file:/x.png]",
        occurred_at=_at(10),
        tool_call=_FULL_SEND_TOOL,
    )
    await _save(
        uow_factory,
        event_id="tool:call-load",
        text="",
        occurred_at=_at(20),
        tool_call=_COMPACT_SUCCESS,
    )
    manager, _queue = _make_manager(_FakeAdapter(), uow_factory)

    records = await manager._load_recent_self_messages(ConversationRef(kind="group", id=GROUP_KEY), {str(BOT_QQ)}, None)

    assert [record.event_id for record in records] == ["self:-401", "tool:call-load"]
    assert [record.tool_call["compact"] for record in records] == [False, True]
    assert [manager._is_tool_call_record(record) for record in records] == [False, True]


# ── 发送工具：full 历史 ─────────────────────────────────────────────


async def test_restore_send_tool_keeps_full_arguments_and_result(uow_factory):
    """send_reply 图片：恢复后 full 重建（emoji_numbers + image_index 都在）。"""
    await _save(
        uow_factory,
        event_id="self:-101",
        text="[图片:tmp_abc file:/x.png]",
        occurred_at=_at(20),
        tool_call=_FULL_SEND_TOOL,
    )
    queue = await _restore(
        uow_factory,
        [_backend_message(1, USER_QQ, "早", _epoch(0)), _backend_message(2, USER_QQ, "喂", _epoch(60))],
    )

    assert _texts(queue) == ["早", "[图片:tmp_abc file:/x.png]", "喂"]
    messages = _rebuilt(queue)
    assert [item["role"] for item in messages] == ["user", "assistant", "tool", "user"]

    call = _calls(messages)[0]
    function = call["function"]
    assert function["name"] == "send_reply"
    assert json.loads(function["arguments"]) == {"emoji_numbers": [1]}
    result = json.loads(_results(messages)[0]["content"])
    assert result["image_index"] == "[图片:tmp_abc file:/x.png]"
    assert call["id"] == _results(messages)[0]["tool_call_id"] == "call-image"


async def test_restore_send_tool_with_text_record_via_production_writer(uow_factory, tmp_path):
    """端到端：ReplySender 落盘的图片记录 -> 重启恢复 -> full 工具历史。"""
    image = tmp_path / "a.png"
    image.write_bytes(b"png")

    async def registrar(path):
        return SimpleNamespace(image_id="tmp_abc")

    sender = ReplySender(
        adapter=None,
        file_server=None,
        config=SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ)),
        bot_name="测试机器人",
        self_sent_uow_factory=uow_factory,
        image_registrar=registrar,
    )
    sink = SelfSentSink(queue=MessageQueue(), snapshot=None, queue_key=GROUP_KEY)
    await sender.record_self_sent_image(
        sink,
        ConversationRef(kind="group", id=GROUP_KEY),
        image,
        tool_arguments={"emoji_numbers": [1]},
        bot_account=BOT_QQ,
    )
    await _drain(sender)

    queue = await _restore(uow_factory, [_backend_message(1, USER_QQ, "看图", _epoch(0))])
    call = _calls(_rebuilt(queue))[0]
    assert call["function"]["name"] == "send_reply"
    assert json.loads(call["function"]["arguments"]) == {"emoji_numbers": [1]}
    assert "[图片:tmp_abc" in json.loads(_results(_rebuilt(queue))[0]["content"])["image_index"]


# ── 非发送工具：compact 历史 ────────────────────────────────────────


async def test_restore_compact_tool_success_hides_arguments_and_result(uow_factory):
    """非发送工具成功：只恢复工具名 + ok，参数/结果内容不进聊天历史。"""
    await _save(
        uow_factory,
        event_id="tool:call-search-ok",
        text="",
        occurred_at=_at(10),
        tool_call=_COMPACT_SUCCESS,
    )
    queue = await _restore(
        uow_factory,
        [_backend_message(1, USER_QQ, "早", _epoch(0)), _backend_message(2, USER_QQ, "喂", _epoch(60))],
    )

    assert _texts(queue) == ["早", "喂"]
    messages = _rebuilt(queue)
    assert [item["role"] for item in messages] == [
        "user",
        "assistant",
        "tool",
        "user",
    ]
    call = _calls(messages)[0]
    assert call["function"]["name"] == "web_search"
    assert call["function"]["arguments"] == "{}"
    assert json.loads(_results(messages)[0]["content"]) == {"ok": True}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert _SECRET_ARG not in rendered
    assert _SECRET_RESULT not in rendered


async def test_restore_compact_tool_failure_only_reports_ok_false(uow_factory):
    """非发送工具失败：只显示 ok:false，错误正文/参数不泄漏。"""
    await _save(
        uow_factory,
        event_id="tool:call-search-fail",
        text="",
        occurred_at=_at(10),
        tool_call=_COMPACT_FAILURE,
    )
    queue = await _restore(uow_factory, [_backend_message(1, USER_QQ, "查一下", _epoch(0))])

    messages = _rebuilt(queue)
    call = _calls(messages)[0]
    assert call["function"]["name"] == "web_search"
    assert call["function"]["arguments"] == "{}"
    assert json.loads(_results(messages)[0]["content"]) == {"ok": False}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert _SECRET_ARG not in rendered
    assert _SECRET_RESULT not in rendered


async def test_restore_compact_tool_via_production_writer(uow_factory):
    """端到端：sender.persist_tool_call 写入的 tool: 记录能被启动恢复还原。"""
    from neobot_app.message.queue import SelfSentToolCall

    sender = ReplySender(
        adapter=None,
        file_server=None,
        config=SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ)),
        bot_name="测试机器人",
        self_sent_uow_factory=uow_factory,
    )
    await sender.persist_tool_call(
        ConversationRef(kind="group", id=GROUP_KEY),
        SelfSentToolCall(
            name="web_search",
            arguments={"q": _SECRET_ARG},
            result={"ok": True, "value": _SECRET_RESULT},
            ok=True,
            compact=True,
            call_id="call-e2e",
        ),
        occurred_at=_at(10),
        bot_account=BOT_QQ,
    )

    queue = await _restore(uow_factory, [_backend_message(1, USER_QQ, "早", _epoch(0))])
    messages = _rebuilt(queue)
    assert [item["role"] for item in messages] == ["user", "assistant", "tool"]
    assert _calls(messages)[0]["id"] == "call-e2e"
    assert _SECRET_ARG not in json.dumps(messages, ensure_ascii=False)


# ── 空正文与顺序 ───────────────────────────────────────────────────


async def test_restore_never_emits_blank_messages_for_empty_tool_records(uow_factory):
    """空 text 的工具记录 / 空聊天记录都不能恢复成空白用户或 assistant 消息。"""
    await _save(
        uow_factory,
        event_id="tool:empty",
        text="",
        occurred_at=_at(10),
        tool_call=_COMPACT_SUCCESS,
    )
    await _save(uow_factory, event_id="self:-empty", text="", occurred_at=_at(20))
    await _save(
        uow_factory,
        event_id="self:-real",
        text="真实回复",
        occurred_at=_at(30),
    )

    queue = await _restore(uow_factory, [_backend_message(1, USER_QQ, "在吗", _epoch(0))])

    assert _texts(queue) == ["在吗", "真实回复"]
    messages = _rebuilt(queue)
    for message in messages:
        if message.get("role") == "assistant" and not message.get("tool_calls"):
            assert message.get("content"), "assistant 不能有空白正文消息"
        if message.get("role") == "user":
            assert str(message.get("content") or "").strip(), "user 不能有空白正文消息"


async def test_restore_merges_into_existing_queue_by_occurred_at(uow_factory):
    """已有队列条目 + 本地工具/聊天记录按 occurred_at 合并（顺序稳定）。"""
    await _save(
        uow_factory,
        event_id="self:-201",
        text="本地回复",
        occurred_at=_at(20),
        tool_call=_FULL_SEND_TOOL,
    )
    await _save(
        uow_factory,
        event_id="tool:call-order",
        text="",
        occurred_at=_at(30),
        tool_call=_COMPACT_SUCCESS,
    )
    manager, queue = _make_manager(_FakeAdapter(), uow_factory)
    queue.push_history(
        GROUP_KEY,
        _converted(_backend_message(1, USER_QQ, "早", _epoch(10))),
        occurred_at=_epoch(10),
    )

    await manager._merge_self_sent_history(
        queue=queue,
        queue_key=GROUP_KEY,
        conversation=ConversationRef(kind="group", id=GROUP_KEY),
        backend_messages=[_backend_message(1, USER_QQ, "早", _epoch(10))],
        limit=30,
    )

    assert _texts(queue) == ["早", "本地回复"]
    roles = _roles(queue)
    assert roles == ["user", "assistant", "tool", "assistant", "tool"]
    call_names = [call["function"]["name"] for call in _calls(_rebuilt(queue))]
    assert call_names == ["send_reply", "web_search"]


def _converted(message):
    from neobot_adapter.utils.parse import safe_parse_model
    from neobot_adapter.model.message import GroupMessage

    return safe_parse_model(message.model_dump(), GroupMessage)


async def test_restore_same_timestamp_order_is_stable(uow_factory):
    """occurred_at 相同的消息与工具调用：多次恢复得到同一顺序（缓存前缀稳定）。"""
    await _save(
        uow_factory,
        event_id="self:-301",
        text="同时刻回复",
        occurred_at=_at(10),
        tool_call=_FULL_SEND_TOOL,
    )
    await _save(
        uow_factory,
        event_id="tool:call-same-time",
        text="",
        occurred_at=_at(10),
        tool_call=_COMPACT_SUCCESS,
    )

    first = _rebuilt(await _restore(uow_factory))
    second = _rebuilt(await _restore(uow_factory))

    assert first == second
    assert [call["id"] for call in _calls(first)] == ["call-image", "call-search-ok"]


# ── 队列裁剪 ───────────────────────────────────────────────────────


async def test_restore_trims_with_consistent_tool_pairs(uow_factory):
    """队列容量裁剪后，恢复出的 tool_calls 与 tool 回执仍一一配对。"""
    for index in range(12):
        await _save(
            uow_factory,
            event_id=f"tool:call-trim-{index}",
            text="",
            occurred_at=_at(index),
            tool_call={**_COMPACT_SUCCESS, "call_id": f"call-trim-{index}"},
        )
    await _save(
        uow_factory,
        event_id="self:-trim",
        text="最后一条回复",
        occurred_at=_at(20),
        tool_call=_FULL_SEND_TOOL,
    )
    queue = await _restore(uow_factory, max_size=1)

    messages = _rebuilt(queue)
    call_ids = [call["id"] for call in _calls(messages)]
    result_ids = [result["tool_call_id"] for result in _results(messages)]
    assert call_ids == result_ids
    assert 0 < len(call_ids) < 13, "裁剪应丢弃最旧条目，而不是全部保留"
    assert "最后一条回复" in _texts(queue)
