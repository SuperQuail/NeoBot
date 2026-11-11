"""官方机器人：只有真正的 @ 才算被 @。

GROUP_AT_MESSAGE_CREATE 由适配器在消息头补一个指向机器人 self_id 的 at 段；
GROUP_MESSAGE_CREATE（群全量消息）没有 at 段时不得按 @ 处理，否则每条群消息
都会触发必回。账号解析完成前用消息级 self_id 兜底。
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


def test_official_full_group_message_without_at_is_not_mention() -> None:
    """群全量消息没有 @：不能当 @，否则每条群消息都会触发必回。"""
    service = _service("official")
    assert service.is_at_mentioned(_group_message()) is False


def test_official_at_event_counts_before_account_is_resolved() -> None:
    """@ 事件由适配器补 at 段（qq=self_id）；账号解析完成前也要认出来。"""
    config = _config()
    config.bot.account = 0
    service = _service("official", config)
    assert service.is_at_mentioned(_group_message(at_qq=_BOT_ACCOUNT)) is True


def test_official_full_group_message_with_explicit_at_counts() -> None:
    service = _service("official")
    assert service.is_at_mentioned(_group_message(at_qq=_BOT_ACCOUNT)) is True


def test_official_full_group_message_at_other_user_is_not_mention() -> None:
    service = _service("official")
    assert service.is_at_mentioned(_group_message(at_qq=_OTHER_ACCOUNT)) is False


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
    assert service.is_at_mentioned(_group_message(at_qq=_BOT_ACCOUNT)) is False
