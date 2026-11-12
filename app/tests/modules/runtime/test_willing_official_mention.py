"""官方机器人：被 @ 由适配器 mentioned_self 权威判定，None 回退 OneBot at 段。

GROUP_AT_MESSAGE_CREATE 本身就是 @ 事件（content 无 @ 前缀），适配器写
mentioned_self=True，app 侧不得再靠 at 段/通道名/uin 猜；GROUP_MESSAGE_CREATE
只有明确引用机器人时才是 True。旧消息没有该字段（None）时回退 at 段逻辑。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.model.message import GroupMessage, MessageSegment, PrivateMessage
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.willing.service import WillingService

_BOT_ACCOUNT = 123456
_OTHER_ACCOUNT = 999


def _config(*, guaranteed: bool = True) -> BotConfig:
    config = BotConfig()
    config.bot.account = _BOT_ACCOUNT
    config.chat.at_mention_guaranteed_reply = guaranteed
    return config


def _service(kind: str | None, config: BotConfig | None = None) -> WillingService:
    profile = None if kind is None else SimpleNamespace(kind=kind)
    detector = SimpleNamespace(profile=profile)
    return WillingService(config or _config(), bot_detector=detector)


def _group_message(*, at_qq: int | None = None, self_id: int = _BOT_ACCOUNT) -> GroupMessage:
    segments = []
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": at_qq}))
    segments.append(MessageSegment(type="text", data={"text": "在吗"}))
    return GroupMessage(
        message_id=1,
        user_id=10001,
        group_id=123456,
        self_id=self_id,
        message=segments,
        raw_message="在吗",
    )


def _official_message(
    *,
    mentioned_self: bool | None,
    at_qq: int | None = None,
    self_id: int = 0,
) -> GroupMessage:
    segments = []
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": at_qq}))
    segments.append(MessageSegment(type="text", data={"text": "在吗"}))
    return GroupMessage(
        message_id=1,
        user_id="user_openid",
        group_id="group_openid",
        self_id=self_id,
        message=segments,
        raw_message="在吗",
        neobot_channel="official",
        mentioned_self=mentioned_self,
    )


def test_official_at_event_counts_without_at_segment() -> None:
    """原生 @ 事件：uin 未解析、没有 at 段，也按 mentioned_self=True 算被 @。"""
    service = _service("official")
    assert service.is_at_mentioned(_official_message(mentioned_self=True)) is True


def test_official_full_group_message_without_at_is_not_mention() -> None:
    """群全量消息未 @ 机器人：mentioned_self=False，不算被 @。"""
    service = _service("official")
    assert service.is_at_mentioned(_official_message(mentioned_self=False)) is False


def test_official_mentioned_self_false_ignores_matching_at_segment() -> None:
    """官方权威结论 False 时不再看 at 段，避免全量消息被旧补丁误判为 @。"""
    service = _service("official")
    message = _official_message(mentioned_self=False, at_qq=_BOT_ACCOUNT, self_id=_BOT_ACCOUNT)
    assert service.is_at_mentioned(message) is False


def test_official_mentioned_self_none_falls_back_to_at_segment() -> None:
    """旧消息没有 mentioned_self：回退 at 段（qq=self_id）判定。"""
    service = _service("official")
    message = _official_message(mentioned_self=None, at_qq=_BOT_ACCOUNT)
    assert service.is_at_mentioned(message) is True


def test_official_channel_without_marker_or_at_is_not_mention() -> None:
    """不再按官方通道无条件判 @：None + 无 at 段不算。"""
    service = _service("official")
    assert service.is_at_mentioned(_official_message(mentioned_self=None)) is False


def test_unofficial_group_message_without_at_segment_keeps_original_logic() -> None:
    service = _service("unofficial")
    assert service.is_at_mentioned(_group_message()) is False


def test_unofficial_group_message_with_at_segment_still_counts() -> None:
    service = _service("unofficial")
    assert service.is_at_mentioned(_group_message(at_qq=_BOT_ACCOUNT)) is True


def test_official_private_message_keeps_original_logic() -> None:
    service = _service("official")
    message = PrivateMessage(
        message_id=2,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": "你好"})],
        raw_message="你好",
    )
    assert service.is_at_mentioned(message) is False


def test_unresolved_profile_falls_back_to_at_segment_logic() -> None:
    service = _service(None)
    assert service.is_at_mentioned(_group_message()) is False


def test_guaranteed_reply_disabled_still_respected() -> None:
    service = _service("official", _config(guaranteed=False))
    assert service.is_at_mentioned(_official_message(mentioned_self=True)) is False
