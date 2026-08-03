"""message/process 测试：历史/事件消息与通知的文本化及事件字典解析。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_adapter.model.notice import (
    GroupMessageDelete,
    GroupPoke,
    GroupIncrease,
    PrivateMessageDelete,
    PrivatePoke,
)
from neobot_adapter.model.response import (
    BasicMessageData,
    GetSignalMsgData,
    GetSignalMsgResponse,
    MessageData,
)
from neobot_app.message.process import (
    _notice,
    _parse_cq_code,
    event_message__to_text,
    history_message_to_text,
    notice_to_text,
)


def _signal_data(*segments: tuple[str, dict]) -> GetSignalMsgData:
    """构造 GetSignalMsgData（历史消息数据）。"""
    return GetSignalMsgData(
        user_id=123,
        message_id=456,
        message=[
            MessageData(type=t, data=BasicMessageData(**d))
            for t, d in segments
        ],
    )


async def test_history_message_to_text_renders_common_segments() -> None:
    """Arrange: 含 text/image/未知类型的消息数据；Act: history_message_to_text 转换；Assert: 各段按预期拼接且未知类型有兜底文案。"""
    message = _signal_data(
        ("text", {"text": "你好"}),
        ("image", {"file": "a.jpg"}),
        ("mystery", {"k": "v"}),
    )

    text = await history_message_to_text(message)

    assert text == "QQ:123: 你好图片 [a.jpg]未知消息类型 [mystery]"


@pytest.mark.xfail(
    reason=(
        "BUG-PROC-001 history_message_to_text 遇到 at 消息段时崩溃：BasicMessageData"
        " 没有 name/qq 字段，item.data.name 触发 AttributeError"
    ),
    strict=False,
)
async def test_history_message_to_text_renders_at_segment_without_crash() -> None:
    """Arrange: 含 at 消息段的历史消息；Act: history_message_to_text；Assert: 不崩溃且输出包含被 @ 的用户名。"""
    message = _signal_data(("at", {"qq": 888, "name": "小群"}))

    text = await history_message_to_text(message)

    assert "小群" in text


async def test_history_message_to_text_uses_stranger_info_nickname() -> None:
    """Arrange: 提供返回昵称的 get_stranger_info；Act: 转换同一条消息；Assert: 昵称优先、未注入时退化为 QQ 号。"""
    message = _signal_data(("text", {"text": "hi"}))
    getter = AsyncMock(return_value=SimpleNamespace(data=SimpleNamespace(nickname="小美")))

    text_with_info = await history_message_to_text(message, get_stranger_info=getter)
    text_without_info = await history_message_to_text(message)

    assert text_without_info == "QQ:123: hi"
    assert text_with_info == "小美: hi"
    getter.assert_awaited_once_with(123)


async def test_history_message_to_text_rejects_unsupported_type() -> None:
    """Arrange: 既非 GetSignalMsgResponse 也非 GetSignalMsgData 的对象；Act: 转换；Assert: 抛出 TypeError。"""
    with pytest.raises(TypeError, match="Unsupported message type"):
        await history_message_to_text("not-a-message")


async def test_history_message_to_text_accepts_response_wrapper() -> None:
    """Arrange: GetSignalMsgResponse 包装同一数据；Act: 转换；Assert: 输出与直接传 GetSignalMsgData 一致。"""
    data = _signal_data(("text", {"text": "wrapped"}))
    response = GetSignalMsgResponse(status="ok", retcode=0, data=data)

    assert await history_message_to_text(response) == await history_message_to_text(data)


async def test_event_message_to_text_uses_segments_and_falls_back_to_raw_cq() -> None:
    """Arrange: 结构化段消息、仅 raw_message 消息、双空消息；Act: event_message__to_text；Assert: 分别命中段渲染/CQ 解析/无内容兜底。"""
    sender = PostMessageMessagesender(user_id=7, nickname="tester")
    structured = GroupMessage(
        message_id=1,
        user_id=7,
        group_id=42,
        sender=sender,
        message=[
            MessageSegment(type="text", data={"text": "结构化"}),
            MessageSegment(type="face", data={"id": "14"}),
        ],
        raw_message="",
    )
    raw = GroupMessage(
        message_id=2,
        user_id=7,
        group_id=42,
        sender=sender,
        message=[],
        raw_message="普通文本[CQ:image,file=x.png]结尾",
    )
    empty = GroupMessage(
        message_id=3, user_id=7, group_id=42, sender=sender, message=[], raw_message=""
    )

    assert await event_message__to_text(structured) == "tester: 结构化[CQ:face,id=14]"
    assert await event_message__to_text(raw) == "tester: 普通文本图片 [x.png]结尾"
    assert await event_message__to_text(empty) == "tester: [无消息内容]"


async def test_notice_to_text_covers_recall_poke_and_unknown() -> None:
    """Arrange: 群/私聊撤回、群戳一戳与未知通知对象；Act: notice_to_text；Assert: 各类型文案包含关键字段。"""
    group_delete = GroupMessageDelete(
        group_id=42, user_id=7, operator_id=8, message_id=100
    )
    private_delete = PrivateMessageDelete(user_id=7, message_id=100)
    poke = GroupPoke(group_id=42, user_id=7, target_id=9)

    assert "群消息撤回" in await notice_to_text(group_delete)
    assert "群 42" in await notice_to_text(group_delete)
    assert "私聊消息撤回" in await notice_to_text(private_delete)
    assert "群戳一戳" in await notice_to_text(poke)
    assert await notice_to_text(SimpleNamespace(notice_type=None)) == "未知通知类型 [未知]"


async def test_notice_parses_event_dict_to_typed_notice() -> None:
    """Arrange: 三类事件字典；Act: _notice 解析；Assert: 分别得到对应类型实例且未知类型返回 None。"""
    recall = await _notice(
        {"notice_type": "group_recall", "group_id": 42, "user_id": 7, "operator_id": 8, "message_id": 100}
    )
    group_poke = await _notice(
        {"notice_type": "notify", "sub_type": "poke", "group_id": 42, "user_id": 7, "target_id": 9}
    )
    private_poke = await _notice(
        {"notice_type": "notify", "sub_type": "poke", "user_id": 7, "target_id": 9}
    )
    increase = await _notice(
        {"notice_type": "group_increase", "group_id": 42, "user_id": 7, "operator_id": 8, "sub_type": "invite"}
    )
    unknown = await _notice({"notice_type": "totally_unknown"})

    assert isinstance(recall, GroupMessageDelete)
    assert isinstance(group_poke, GroupPoke)
    assert group_poke.group_id == 42
    assert isinstance(private_poke, PrivatePoke)
    assert isinstance(increase, GroupIncrease)
    assert unknown is None


def test_parse_cq_code_renders_common_types() -> None:
    """Arrange: 含多种 CQ 码的字符串；Act: _parse_cq_code；Assert: 常见类型全部被转换为可读文本。"""
    raw = "看[CQ:at,qq=all]图[CQ:image,file=f.png][CQ:face,id=14][CQ:unknown,x=1]"

    text = _parse_cq_code(raw)

    assert "看@全体成员" in text
    assert "图片 [f.png]" in text
    assert "表情 [14]" in text
    assert "[CQ:unknown]" in text
