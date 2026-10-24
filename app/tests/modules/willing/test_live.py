"""直播意愿判断：@ 保证与独立于 QQ 群的会话 id。"""

from __future__ import annotations

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.willing.service import WillingService


def test_evaluate_live_mentions_bot_is_guaranteed(monkeypatch) -> None:
    config = BotConfig()
    config.bot.nick_name = "小助手"
    config.bot.account = 123
    config.chat.at_mention_guaranteed_reply = True
    service = WillingService(config)

    decision = service.evaluate_live(
        room_id=5440,
        uid=9,
        name="观众",
        text="小助手 在吗",
        observed_messages=(),
    )

    assert decision.should_reply is True
    assert "被@或被叫名字" in " ".join(decision.reasons)


def test_evaluate_live_uses_live_conversation_id(monkeypatch) -> None:
    config = BotConfig()
    service = WillingService(config)
    captured = {}
    original = service._manager.evaluate

    def _capture(context):
        captured["conversation_id"] = context.conversation_id
        captured["is_allowed"] = context.is_allowed
        return original(context)

    monkeypatch.setattr(service._manager, "evaluate", _capture)
    service.evaluate_live(room_id=5440, uid=9, name="观众", text="在吗")

    assert captured["conversation_id"] == "live:5440"
    assert captured["is_allowed"] is True


def test_live_runtime_coefficient_keeps_live_prefix(monkeypatch) -> None:
    """live:<room> 的运行时系数必须带前缀存取：剥前缀会串到同号 QQ 群。"""
    config = BotConfig()
    service = WillingService(config)

    service.set_runtime_conversation_coefficient("live:5440", 0.5)

    assert service.get_runtime_conversation_coefficient("live:5440") == 0.5
    assert service._runtime_config.conversation_coefficients.get("live:5440") == 0.5
    assert service._runtime_config.conversation_coefficients.get("5440") is None, (
        "直播间的系数不得写进同号 QQ 群的键"
    )

    service.remove_runtime_conversation_coefficient("live:5440")
    assert service.get_runtime_conversation_coefficient("live:5440") is None


def test_live_runtime_blacklist_blocks_live_room(monkeypatch) -> None:
    """拉黑直播间 live:<room> 后，该直播间的弹幕必须被判屏蔽。"""
    config = BotConfig()
    service = WillingService(config)

    service.add_runtime_blacklist("live:5440")
    decision = service.evaluate_live(
        room_id=5440,
        uid=9,
        name="观众",
        text="在吗？",
        base_probability=1.0,
        mentioned=True,
    )

    assert decision.should_reply is False
    assert "运行时黑名单" in " ".join(decision.reasons)
