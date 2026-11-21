"""插件公开事件视图的本地 ID 类型：OneBot int 与官方 openid 字符串共存。"""

from __future__ import annotations

from neobot_modloader.events import IncomingEvent


def test_numeric_ids_stay_int() -> None:
    event = IncomingEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123456,
            "user_id": 42,
            "self_id": 10001,
            "sender": {"user_id": 42, "nickname": "甲"},
        }
    )

    assert event.user_id == 42
    assert event.group_id == 123456
    assert event.scope == ("10001", "group", "123456", "42")


def test_openid_strings_are_passed_through() -> None:
    event = IncomingEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": "A1B2C3D4E5F6",
            "user_id": "2F1B3C4D5E6F7A8B",
            "self_id": 10001,
            "sender": {"user_id": "2F1B3C4D5E6F7A8B", "nickname": "官方用户"},
        }
    )

    # 不转 int（会 ValueError / 丢精度），也不改写原值。
    assert event.user_id == "2F1B3C4D5E6F7A8B"
    assert event.group_id == "A1B2C3D4E5F6"
    assert event.scope == ("10001", "group", "A1B2C3D4E5F6", "2F1B3C4D5E6F7A8B")
    assert event.sender.user_id == "2F1B3C4D5E6F7A8B"


def test_missing_ids_are_none() -> None:
    event = IncomingEvent({"post_type": "message"})

    assert event.user_id is None
    assert event.group_id is None
