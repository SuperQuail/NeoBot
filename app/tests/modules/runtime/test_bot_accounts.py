"""统一机器人 QQ 号提供者的单通道/双通道语义。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.bot_accounts import (
    BotAccounts,
    bind_bot_accounts,
    bot_account_for_channel,
    bot_account_for_event,
    bot_account_for_message,
    bot_accounts,
    get_bot_accounts,
    is_bot_message,
    looks_like_real_qq,
    primary_bot_account,
)


class _Detector:
    def __init__(self, accounts: dict[str, int], primary: int) -> None:
        self.accounts = dict(accounts)
        self.profile = SimpleNamespace(account=primary)

    def account_for(self, channel: str) -> int:
        return int(self.accounts.get(channel, 0) or 0)


@pytest.fixture(autouse=True)
def _reset_provider():
    bind_bot_accounts(None, None)
    yield
    bind_bot_accounts(None, None)


def _config(account: int = 0):
    return SimpleNamespace(bot=SimpleNamespace(account=account))


def _message(**kwargs):
    defaults = {"self_id": None, "user_id": None, "neobot_channel": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _event(**kwargs):
    defaults = {"bot_account": 0, "neobot_channel": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_unbound_falls_back_to_config():
    bind_bot_accounts(_config(90001), None)
    assert primary_bot_account() == 90001
    assert bot_accounts() == {90001}
    assert bot_account_for_message(_message(user_id=1)) == 90001
    assert bot_account_for_channel("official") == 90001
    assert bot_account_for_event(_event()) == 90001


def test_dual_channel_accounts_come_from_detector():
    detector = _Detector({"onebot": 11111, "official": 22222}, primary=11111)
    bind_bot_accounts(_config(0), detector)

    assert primary_bot_account() == 11111
    assert bot_accounts() == {11111, 22222}
    assert bot_account_for_channel("onebot") == 11111
    assert bot_account_for_channel("official") == 22222
    assert bot_account_for_channel(None) == 11111
    # 消息级 self_id 最优先（官方事件带自己的号）
    assert bot_account_for_message(_message(self_id=22222, user_id=33333)) == 22222
    assert bot_account_for_message(_message(neobot_channel="official")) == 22222
    assert bot_account_for_event(_event(bot_account=22222)) == 22222
    assert bot_account_for_event(_event(neobot_channel="official")) == 22222


def test_is_bot_message_covers_both_channels_and_self_id():
    detector = _Detector({"onebot": 11111, "official": 22222}, primary=11111)
    bind_bot_accounts(_config(0), detector)

    assert is_bot_message(_message(self_id=22222, user_id=22222))
    assert is_bot_message(_message(user_id=11111))
    assert not is_bot_message(_message(self_id=22222, user_id=33333))
    assert not is_bot_message(_message(user_id=33333))


def test_provider_object_is_registered_singleton():
    bind_bot_accounts(_config(90001), None)
    provider = get_bot_accounts()
    assert isinstance(provider, BotAccounts)
    assert provider.primary() == 90001
    assert provider.is_bot_id(90001)
    assert not provider.is_bot_id(90002)


def test_display_labels_follow_id_scale():
    from neobot_app.bot_accounts import display_user_id, id_label

    assert id_label(123456) == "QQ"
    assert display_user_id(123456) == "QQ:123456"
    assert id_label(9000000000001) == "ID"
    assert display_user_id(9000000000001) == "ID:9000000000001"
    assert display_user_id("") == ""


def test_looks_like_real_qq_rejects_synthetic_ids():
    assert looks_like_real_qq(123456789)
    assert looks_like_real_qq("1234567890")
    assert not looks_like_real_qq(9000000000001)  # 官方 13 位合成号
    assert not looks_like_real_qq("abc")
    assert not looks_like_real_qq(0)


def test_rebind_picks_up_new_generation():
    bind_bot_accounts(_config(90001), None)
    assert primary_bot_account() == 90001
    bind_bot_accounts(_config(0), _Detector({"official": 22222}, primary=22222))
    assert primary_bot_account() == 22222
    assert bot_accounts() == {22222}
