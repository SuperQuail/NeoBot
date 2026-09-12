"""ChatHistorySkill 测试：read_earlier_messages 的数据源、兜底与参数收敛。

旧实现把整条 GetHistoryMsgListResponse 当成列表调用 len()，22 次调用 22 次失败：
真实消息在 response.data.messages 里，且需要渲染成可读文本后再交给模型。
"""

from __future__ import annotations

import json

import pytest

from neobot_adapter.model.response import (
    BasicMessageData,
    GetHistoryMsgListData,
    GetHistoryMsgListResponse,
    GetSignalMsgData,
    MessageData,
    MessageSender,
)

from neobot_app.skills.chat_history import ChatHistorySkill


def _item(
    user_id: int = 10001,
    nickname: str = "用户1",
    segments: list | None = None,
    message_seq: int = 1,
) -> GetSignalMsgData:
    if segments is None:
        segments = [("text", {"text": "你好"})]
    return GetSignalMsgData(
        user_id=user_id,
        message_id=message_seq,
        message_seq=message_seq,
        sender=MessageSender(user_id=user_id, nickname=nickname),
        message=[
            MessageData(type=kind, data=BasicMessageData(**payload))
            for kind, payload in segments
        ],
    )


def _response(items: list | None) -> GetHistoryMsgListResponse:
    return GetHistoryMsgListResponse(
        status="ok",
        retcode=0,
        data=GetHistoryMsgListData(messages=items),
    )


class _FakeAdapter:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list = []

    async def get_group_msg_history(
        self, group_id, message_seq=0, count=20, reverse_order=False
    ):
        self.calls.append(("group", group_id, message_seq, count, reverse_order))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def get_friend_msg_history(
        self, user_id, message_seq=0, count=20, reverse_order=False
    ):
        self.calls.append(("private", user_id, message_seq, count, reverse_order))
        return self._response


async def _run(adapter, args: dict) -> dict:
    skill = ChatHistorySkill(adapter=adapter)
    return json.loads(await skill.execute("read_earlier_messages", args))


@pytest.mark.asyncio
async def test_returns_rendered_text_with_sender_name():
    """data.messages 里的每条消息都要渲染成「昵称: 内容」，不是 pydantic repr。"""
    adapter = _FakeAdapter(_response([
        _item(user_id=10001, nickname="甲", message_seq=1),
        _item(user_id=10002, nickname="乙", segments=[("text", {"text": "在的"})], message_seq=2),
    ]))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is True
    assert result["count"] == 2
    assert result["truncated"] is False
    assert result["messages"][0] == "甲: 你好"
    assert result["messages"][1] == "乙: 在的"
    assert adapter.calls == [("group", 888888, 0, 20, False)]


@pytest.mark.asyncio
async def test_private_conversation_uses_friend_history():
    adapter = _FakeAdapter(_response([_item()]))

    result = await _run(adapter, {"conversation_kind": "private", "conversation_id": "12345"})

    assert result["ok"] is True
    assert adapter.calls == [("private", 12345, 0, 20, False)]


@pytest.mark.asyncio
async def test_data_none_reports_error_without_raising():
    """API 失败时 safe_parse_model 给出 data=None，必须兜底成 ok=false。"""
    adapter = _FakeAdapter(GetHistoryMsgListResponse(status="failed", retcode=1200, wording="取不到"))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is False
    assert "取不到" in result["error"]


@pytest.mark.asyncio
async def test_empty_message_list_reports_error():
    adapter = _FakeAdapter(_response([]))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_messages_none_reports_error():
    adapter = _FakeAdapter(GetHistoryMsgListResponse(status="ok", data=GetHistoryMsgListData(messages=None)))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw,expected",
    [(None, 20), ("abc", 20), ("", 20), (999, 50), (-3, 1), ("7", 7)],
)
async def test_count_is_coerced_and_clamped(raw, expected):
    adapter = _FakeAdapter(_response([_item()]))

    result = await _run(adapter, {
        "conversation_kind": "group", "conversation_id": "888888", "count": raw,
    })

    assert result["ok"] is True
    assert adapter.calls[0][3] == expected


@pytest.mark.asyncio
async def test_invalid_message_seq_and_reverse_order_do_not_raise():
    """message_seq 非法回落 0；reverse_order 传字符串 "false" 不得被当成 True。"""
    adapter = _FakeAdapter(_response([_item()]))

    result = await _run(adapter, {
        "conversation_kind": "group",
        "conversation_id": "888888",
        "message_seq": "null",
        "reverse_order": "false",
    })

    assert result["ok"] is True
    assert adapter.calls[0][2] == 0
    assert adapter.calls[0][4] is False


@pytest.mark.asyncio
async def test_bad_conversation_kind_and_id_are_rejected_before_api_call():
    adapter = _FakeAdapter(_response([_item()]))

    bad_kind = await _run(adapter, {"conversation_kind": "群聊", "conversation_id": "888888"})
    bad_id = await _run(adapter, {"conversation_kind": "group", "conversation_id": "abc"})

    assert bad_kind["ok"] is False and "conversation_kind" in bad_kind["error"]
    assert bad_id["ok"] is False and "conversation_id" in bad_id["error"]
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_renders_text_image_at_and_forward_segments():
    adapter = _FakeAdapter(_response([_item(nickname="甲", segments=[
        ("text", {"text": "看这个"}),
        ("image", {"file": "a.png"}),
        ("at", {"name": "乙", "qq": 10002}),
        ("forward", {"id": "fwd-1"}),
    ])]))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    text = result["messages"][0]
    assert text.startswith("甲: 看这个")
    assert "图片 [a.png]" in text
    assert "@乙(QQ:10002)" in text
    assert "合并转发" in text


@pytest.mark.asyncio
async def test_output_budget_truncates_and_flags():
    """超出总字符预算时必须裁剪条数并给出 truncated=true。"""
    items = [
        _item(user_id=10000 + i, nickname=f"用户{i}",
              segments=[("text", {"text": "长" * 500})], message_seq=i)
        for i in range(20)
    ]
    adapter = _FakeAdapter(_response(items))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888", "count": 20})

    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["count"] < 20
    assert len(result["messages"]) == result["count"]


@pytest.mark.asyncio
async def test_long_single_message_is_clipped():
    adapter = _FakeAdapter(_response([_item(segments=[("text", {"text": "超" * 2000})])]))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is True
    assert len(result["messages"][0]) <= 601


@pytest.mark.asyncio
async def test_adapter_exception_is_reported_not_propagated():
    adapter = _FakeAdapter(RuntimeError("boom"))

    result = await _run(adapter, {"conversation_kind": "group", "conversation_id": "888888"})

    assert result["ok"] is False
    assert "RuntimeError" in result["error"]
