"""官方机器人：群消息一律按 @ 机器人处理。

官方群事件只在被 @ 时才推送，消息里未必带 at 段；账号解析完成前 bot.account
还没填、at 段也对不上。非官方通道的判定逻辑保持原样（仍看 at 段）。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.model.message import GroupMessage, MessageSegment, PrivateMessage
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.willing.service import WillingService

_BOT_ACCOUNT = 123456


def _config(*, guaranteed: bool = True) -> BotConfig:
    config = BotConfig()
    config.bot.account = _BOT_ACCOUNT
    config.chat.at_mention_guaranteed_reply = guaranteed
    return config


def _service(kind: str | None, config: BotConfig | None = None) -> WillingService:
    profile = None if kind is None else SimpleNamespace(kind=kind)
    detector = SimpleNamespace(profile=profile)
    return WillingService(config or _config(), bot_detector=detector)


def _group_message(*, with_at: bool = False) -> GroupMessage:
    segments = []
    if with_at:
        segments.append(MessageSegment(type="at", data={"qq": _BOT_ACCOUNT}))
    segments.append(MessageSegment(type="text", data={"text": "在吗"}))
    return GroupMessage(
        message_id=1,
        user_id=10001,
        group_id=123456,
        message=segments,
        raw_message="在吗",
    )


def test_official_group_message_without_at_segment_counts_as_mention() -> None:
    service = _service("official")
    assert service.is_at_mentioned(_group_message()) is True


def test_official_group_message_still_counts_before_account_is_resolved() -> None:
    """账号解析完成前 bot.account 可能是 0：at 段对不上也要按 @ 处理。"""
    config = _config()
    config.bot.account = 0
    service = _service("official", config)
    assert service.is_at_mentioned(_group_message()) is True


def test_unofficial_group_message_without_at_segment_keeps_original_logic() -> None:
    service = _service("unofficial")
    assert service.is_at_mentioned(_group_message()) is False


def test_unofficial_group_message_with_at_segment_still_counts() -> None:
    service = _service("unofficial")
    assert service.is_at_mentioned(_group_message(with_at=True)) is True


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
    assert service.is_at_mentioned(_group_message()) is False
