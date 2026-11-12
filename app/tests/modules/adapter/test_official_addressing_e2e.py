"""官方 @ 判定端到端：用户真实 GROUP_AT 示例 JSON → 权威 mentioned_self。

用户线上事件的特征：机器人 QQ 号（uin/self_id）尚未解析（self_id=0）、content 已被
官方去掉 @ 机器人前缀（例如 " /今日天气 "）、也可能没有 mentions。按官方 API 契约，
GROUP_AT_MESSAGE_CREATE 事件类型本身就是 @ 机器人；GROUP_MESSAGE_CREATE（群全量消息）
只有 content 的 @ 标记或 mentions/msg_elements 明确指向机器人 openid 时才算 @。

本文件只走适配器侧生产路径：EventMapper.from_dispatch → safe_parse_model(GroupMessage)，
断言事件字典与消息模型上的 mentioned_self 权威结论（True/False 不再靠 at 段/self_id 猜）；
命令触发与必回消费在 runtime/test_official_addressing_integration.py 里验收。
"""

from __future__ import annotations

import itertools
from typing import Any

from neobot_adapter.model.message import GroupMessage
from neobot_adapter.official.events import EventMapper
from neobot_adapter.official.identity import MessageIdMap
from neobot_adapter.utils.parse import safe_parse_model
from neobot_contracts.ports.logging import NullLogger

_EVENT_SEQ = itertools.count(1)


def _dispatch(
    event_type: str,
    data: dict[str, Any],
    *,
    event_id: str | None = None,
    seq: int = 1,
) -> dict[str, Any]:
    return {
        "op": 0,
        "t": event_type,
        "id": event_id or f"evt-{next(_EVENT_SEQ)}",
        "s": seq,
        "d": data,
    }


def _mapper(*, self_id: int = 0, bot_openid: str = "") -> EventMapper:
    """默认 self_id=0：复现「机器人 uin 未解析」的线上状态。"""
    mapper = EventMapper(message_ids=MessageIdMap(), logger=NullLogger(), self_id=self_id)
    mapper.bot_openid = bot_openid
    return mapper


def _user_group_at_payload(
    content: str = " /今日天气 ",
    *,
    message_id: str = "ROBOT1.0_user-example",
    event_id: str | None = None,
) -> dict[str, Any]:
    """用户提供的 GROUP_AT_MESSAGE_CREATE 示例：content 无 @ 前缀、无 mentions。"""
    return _dispatch(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": message_id,
            "content": content,
            "timestamp": "2026-11-12T12:00:00+08:00",
            "group_openid": "group-openid-1",
            "author": {
                "id": "member-openid-1",
                "member_openid": "member-openid-1",
                "union_openid": "union-openid-1",
            },
            "message_scene": {"source": "default", "ext": []},
        },
        event_id=event_id,
    )


def _full_group_payload(
    content: str,
    *,
    message_id: str = "ROBOT1.0_group-msg",
    mentions: list[dict[str, Any]] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": message_id,
        "content": content,
        "timestamp": "2026-11-12T12:00:00+08:00",
        "group_openid": "group-openid-1",
        "author": {"id": "member-openid-1", "member_openid": "member-openid-1"},
    }
    if mentions is not None:
        data["mentions"] = mentions
    return _dispatch("GROUP_MESSAGE_CREATE", data, event_id=event_id)


def _map_and_parse(payload: dict[str, Any], mapper: EventMapper) -> tuple[dict[str, Any], GroupMessage]:
    event = mapper.from_dispatch(payload)
    assert event is not None, "事件映射不应返回 None"
    return event, safe_parse_model(event, GroupMessage)


# ── 用户真实 @ 事件 ─────────────────────────────────────────────────


def test_user_group_at_example_maps_to_authoritative_mention() -> None:
    """self_id=0、无 mentions、content 已去 @ 前缀：仍权威判定被 @。"""
    mapper = _mapper(self_id=0)
    event, message = _map_and_parse(_user_group_at_payload(" /今日天气 "), mapper)

    assert event["post_type"] == "message"
    assert event["message_type"] == "group"
    assert event["self_id"] == 0
    assert event["group_id"] == "group-openid-1"
    assert event["user_id"] == "member-openid-1"
    assert event["mentioned_self"] is True
    # uin 未解析时 at 段 qq=0 只是 OneBot 形状的占位，不再参与判定。
    assert event["message"][0] == {"type": "at", "data": {"qq": 0}}

    assert message.mentioned_self is True
    assert message.group_id == "group-openid-1"
    assert message.user_id == "member-openid-1"
    assert message.message_id and message.message_id > 0
    assert "今日天气" in (message.raw_message or "")


def test_user_group_at_example_for_registered_command_keeps_mention() -> None:
    """用户另一个示例 content=" /reboot "（已注册命令）：映射结论仍是被 @。"""
    mapper = _mapper(self_id=0)
    event, message = _map_and_parse(_user_group_at_payload(" /reboot "), mapper)

    assert event["mentioned_self"] is True
    assert message.mentioned_self is True
    assert "reboot" in (message.raw_message or "")


# ── 群全量消息（GROUP_MESSAGE_CREATE） ──────────────────────────────


def test_full_group_message_without_mention_is_false() -> None:
    """群全量消息没有 @ 机器人：权威结论 False（命令/必回都不得触发）。"""
    mapper = _mapper(bot_openid="bot-openid")
    event, message = _map_and_parse(_full_group_payload("随便聊聊"), mapper)

    assert event["mentioned_self"] is False
    assert message.mentioned_self is False


def test_full_group_message_content_marker_is_true() -> None:
    """content 里 <@!bot_openid> 指向机器人：权威判定被 @。"""
    mapper = _mapper(bot_openid="bot-openid")
    event, message = _map_and_parse(
        _full_group_payload("<@!bot-openid> /今日天气 "),
        mapper,
    )

    assert event["mentioned_self"] is True
    assert message.mentioned_self is True


def test_full_group_message_mentions_bot_entry_is_true() -> None:
    """正文没有标记时，mentions 里 bot=true 且 id==bot_openid 也算被 @。"""
    mapper = _mapper(bot_openid="bot-openid")
    event, message = _map_and_parse(
        _full_group_payload(
            "/今日天气",
            mentions=[
                {"id": "bot-openid", "username": "机器人", "bot": True},
                {"id": "member-openid-2", "username": "小明", "bot": False},
            ],
        ),
        mapper,
    )

    assert event["mentioned_self"] is True
    assert message.mentioned_self is True


def test_full_group_message_other_bot_mention_is_false() -> None:
    """mentions 里是别的机器人：不能冒充本机器人，权威结论 False。"""
    mapper = _mapper(bot_openid="bot-openid")
    event, message = _map_and_parse(
        _full_group_payload(
            "/今日天气",
            mentions=[{"id": "other-bot-openid", "username": "别的机器人", "bot": True}],
        ),
        mapper,
    )

    assert event["mentioned_self"] is False
    assert message.mentioned_self is False


# ── mentioned_self 穿透 safe_parse_model / None 语义 ─────────────────


def test_mentioned_self_survives_safe_parse_model() -> None:
    """权威结论必须原样落在消息模型上（True 与 False 都不能丢成 None）。"""
    mapper = _mapper(bot_openid="bot-openid")

    _, at_message = _map_and_parse(_user_group_at_payload(), mapper)
    _, plain_message = _map_and_parse(_full_group_payload("随便聊聊"), mapper)

    assert at_message.mentioned_self is True
    assert plain_message.mentioned_self is False


def test_non_official_message_mentioned_self_defaults_to_none() -> None:
    """OneBot/旧路径没有权威结论：字段缺省是 None（回退 at 段逻辑）。"""
    message = safe_parse_model(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 1,
            "self_id": 123456,
            "group_id": 42,
            "user_id": 10001,
            "message": [{"type": "text", "data": {"text": "在吗"}}],
            "raw_message": "在吗",
        },
        GroupMessage,
    )

    assert message.mentioned_self is None


# ── AT + FULL 双事件同一消息 ────────────────────────────────────────


def test_at_and_full_events_for_same_message_share_synthetic_id() -> None:
    """同一官方 msg_id 的 AT/FULL 双事件映射到同一个合成 message_id。

    AT 事件由事件类型权威判定被 @；FULL 重复事件即使没有标记也带 False 结论。
    运行期按 message_id 去重时保留先到的那条（消费侧验收见 runtime 集成测试）。
    """
    mapper = _mapper(bot_openid="bot-openid")
    at_event, at_message = _map_and_parse(
        _user_group_at_payload(" /今日天气 ", message_id="ROBOT1.0_same-msg"),
        mapper,
    )
    full_event, full_message = _map_and_parse(
        _full_group_payload(" /今日天气 ", message_id="ROBOT1.0_same-msg"),
        mapper,
    )

    assert at_message.message_id == full_message.message_id
    assert at_event["message_id"] == full_event["message_id"]
    assert at_message.mentioned_self is True
    assert full_message.mentioned_self is False
