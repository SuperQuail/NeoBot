"""@ 判定唯一入口：官方 mentioned_self 权威，None 回退 OneBot at 段。

官方适配器按官方 API 契约给出 mentioned_self（True/False）；app 侧不得再按
通道名、uin、at 段 qq=0 兜底。None 表示非官方/旧路径，回退 OneBot 语义。
"""

from __future__ import annotations

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.addressing import is_addressed_to_bot

BOT = 123456
OTHER = 999


def _config(account: int = BOT) -> BotConfig:
    config = BotConfig()
    config.bot.account = account
    return config


def _group(
    *,
    at_qq: int | None = None,
    self_id: int | None = BOT,
    channel: str | None = None,
    raw_message: str = "在吗",
) -> GroupMessage:
    segments = []
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": str(at_qq)}))
    segments.append(MessageSegment(type="text", data={"text": "在吗"}))
    return GroupMessage(
        message_id=1,
        user_id=10001,
        group_id=42,
        self_id=self_id,
        message=segments,
        raw_message=raw_message,
        neobot_channel=channel,
    )


def _official(*, mentioned_self: bool | None, at_qq: int | None = None, self_id: int = 0) -> GroupMessage:
    """官方消息：只有适配器写的 mentioned_self 参与判定，at 段/通道都不是依据。"""
    segments = []
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": str(at_qq)}))
    segments.append(MessageSegment(type="text", data={"text": "在吗"}))
    return GroupMessage(
        message_id=1,
        user_id="user_openid",
        group_id="group_openid",
        self_id=self_id,
        message=segments,
        raw_message="",
        neobot_channel="official",
        mentioned_self=mentioned_self,
    )


def test_official_mentioned_self_true_is_addressed_without_at_segment() -> None:
    assert is_addressed_to_bot(_official(mentioned_self=True)) is True


def test_official_mentioned_self_false_is_not_addressed() -> None:
    assert is_addressed_to_bot(_official(mentioned_self=False)) is False


def test_official_mentioned_self_false_overrides_matching_at_segment() -> None:
    """官方权威结论为 False 时，at 段/self_id 一律不再参考。"""
    message = _official(mentioned_self=False, at_qq=BOT, self_id=BOT)
    assert is_addressed_to_bot(message) is False


def test_official_mentioned_self_none_falls_back_to_onebot_at_segment() -> None:
    message = _official(mentioned_self=None, at_qq=BOT, self_id=BOT)
    assert is_addressed_to_bot(message) is True


def test_official_channel_without_authoritative_marker_is_not_addressed() -> None:
    """没有官方权威结论时不按通道名无条件判 @。"""
    assert is_addressed_to_bot(_group(channel="official")) is False


def test_at_qq_zero_is_not_treated_as_addressed() -> None:
    """uin 未解析时 at 段 qq=0 不是 @ 依据（旧补丁已删除）。"""
    assert is_addressed_to_bot(_group(at_qq=0, self_id=0), _config(account=0)) is False


def test_onebot_at_segment_to_bot_is_addressed() -> None:
    assert is_addressed_to_bot(_group(at_qq=BOT, channel="onebot")) is True


def test_onebot_at_segment_to_other_user_is_not_addressed() -> None:
    assert is_addressed_to_bot(_group(at_qq=OTHER, channel="onebot")) is False


def test_onebot_without_at_segment_is_not_addressed() -> None:
    assert is_addressed_to_bot(_group(channel="onebot")) is False


def test_falls_back_to_config_account_when_message_self_id_missing() -> None:
    assert is_addressed_to_bot(_group(at_qq=BOT, self_id=None), _config(account=BOT)) is True


def test_raw_message_cq_at_is_fallback_when_segments_missing() -> None:
    message = _group(at_qq=None, raw_message=f"[CQ:at,qq={BOT}] 在吗")
    message.message = None
    assert is_addressed_to_bot(message) is True
