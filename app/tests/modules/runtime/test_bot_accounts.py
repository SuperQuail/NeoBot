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
    display_group_id,
    get_bot_accounts,
    group_label,
    infer_channel,
    is_bot_message,
    is_synthetic_id,
    looks_like_real_group_number,
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


def test_synthetic_id_shape_boundaries():
    """13 位起才是官方合成号；真实 QQ 号（≤11）与群号（≤12）都不算。"""
    assert is_synthetic_id(9000000000001)
    assert is_synthetic_id(8000000000001)
    assert is_synthetic_id("9000000000001")
    assert not is_synthetic_id(12345678901)  # 11 位真实 QQ 号
    assert not is_synthetic_id(123456789012)  # 12 位真实群号
    assert not is_synthetic_id("abc")
    assert not is_synthetic_id(None)
    assert not is_synthetic_id(0)


def test_real_qq_and_group_number_shape_lower_bounds():
    """min_digits 让 /linkqq 这类输入校验不再自己写位数区间。"""
    assert looks_like_real_qq(12345)
    assert looks_like_real_qq(12345678901)
    assert not looks_like_real_qq(123456789012)  # 12 位是群号，不是 QQ 号
    assert looks_like_real_qq(12345, min_digits=5)
    assert not looks_like_real_qq(1234, min_digits=5)

    assert looks_like_real_group_number(123456789012)  # 群号可以到 12 位
    assert not looks_like_real_group_number(9000000000001)
    assert looks_like_real_group_number(12345, min_digits=5)
    assert not looks_like_real_group_number(1234, min_digits=5)
    assert not looks_like_real_group_number("abc")


def test_infer_channel_from_id_shape():
    """通道推断只在没有显式通道时按 ID 规模兜底。"""
    assert infer_channel(123456789) == "onebot"
    assert infer_channel(12345678901) == "onebot"
    assert infer_channel(123456789012) == "official"  # 不传 kind 时按 QQ 号上限
    assert infer_channel(123456789012, kind="group") == "onebot"  # 12 位真实群号
    assert infer_channel(123456789012, kind="private") == "official"
    assert infer_channel(9000000000001) == "official"
    assert infer_channel("abc") == "official"


def test_group_display_labels_follow_group_shape():
    """群号上限 12 位：12 位真实群号不能被标成群 ID。"""
    assert group_label(123456789012) == "群号"
    assert group_label(8000000000001) == "群 ID"
    assert display_group_id(123456789012) == "群号:123456789012"
    assert display_group_id(8000000000001) == "群 ID:8000000000001"
    assert display_group_id("") == ""


def test_rebind_picks_up_new_generation():
    bind_bot_accounts(_config(90001), None)
    assert primary_bot_account() == 90001
    bind_bot_accounts(_config(0), _Detector({"official": 22222}, primary=22222))
    assert primary_bot_account() == 22222
    assert bot_accounts() == {22222}
