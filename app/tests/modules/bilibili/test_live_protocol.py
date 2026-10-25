"""B站直播协议层：多包/压缩、事件映射、protobuf 与去重键。"""

from __future__ import annotations

import base64
import struct
import zlib

import brotli
import pytest

from neobot_app.bilibili.live_protocol import (
    InteractWordV2,
    LiveEvent,
    SendGiftBroadcast,
    SendGiftV2GiftItem,
    check_auth_reply,
    decode_failures,
    decode_packets,
    encode_packet,
    event_key,
    is_mirror,
    parse_danmu_message,
    parse_event,
    parse_events,
)


def test_decode_plain_zlib_brotli_and_multi_packets() -> None:
    plain = encode_packet(5, b'{"cmd":"LIVE"}')
    assert decode_packets(plain) == [(5, b'{"cmd":"LIVE"}')]

    multi = encode_packet(5, b"one") + encode_packet(5, b"two")
    assert decode_packets(multi) == [(5, b"one"), (5, b"two")]

    inner = encode_packet(5, b"a") + encode_packet(5, b"b")
    assert decode_packets(encode_packet(5, zlib.compress(inner), protover=2)) == [(5, b"a"), (5, b"b")]
    assert decode_packets(encode_packet(5, brotli.compress(inner), protover=3)) == [(5, b"a"), (5, b"b")]

    assert decode_packets(encode_packet(8, b'{"code":0}')) == [(8, b'{"code":0}')]
    assert decode_packets(b"") == []
    assert decode_packets(plain[:8]) == []
    assert decode_packets(encode_packet(5, b"not-compressed", protover=3)) == []


def test_decode_failures_are_counted_not_silent() -> None:
    """坏帧/解压失败要计数（并打 debug 日志），不能静默吞掉。"""
    before = decode_failures()

    # total < header_len：包长度异常
    assert decode_packets(struct.pack(">IHHII", 8, 16, 1, 5, 1)) == []
    # protover=2 但不是 zlib 数据
    assert decode_packets(encode_packet(5, b"not-zlib", protover=2)) == []
    # protover=3 但不是 brotli 数据
    assert decode_packets(encode_packet(5, b"not-brotli", protover=3)) == []

    after = decode_failures()
    assert after["frame"] - before.get("frame", 0) == 1
    assert after["zlib"] - before.get("zlib", 0) == 1
    assert after["brotli"] - before.get("brotli", 0) == 1


def test_check_auth_reply() -> None:
    check_auth_reply(b'{"code":0}')
    with pytest.raises(Exception, match="code=-101"):
        check_auth_reply(b'{"code":-101}')
    with pytest.raises(Exception, match="JSON"):
        check_auth_reply(b"not-json")


def test_parse_danmaku_and_mirror() -> None:
    payload = {
        "cmd": "DANMU_MSG:4:0:2:2:2:0",
        "info": [[], "你好", [12345, "观众甲"], [], [], [], [], 3, [], [], [], [], [], [], [], [], [], [0]],
    }
    payload["info"][0] = [0, 1, 25, 16777215, 1700000000123, 111]
    event = parse_event(payload, 5440)
    assert event == LiveEvent("danmaku", 5440, 12345, "观众甲", "你好", 0, 1700000000, payload)
    assert parse_danmu_message(payload) == {"uid": 12345, "name": "观众甲", "text": "你好"}

    assert parse_event({**payload, "cmd": "DANMU_MSG_MIRROR"}, 5440) is None
    assert parse_danmu_message({**payload, "cmd": "DANMU_MSG_MIRROR"}) is None
    assert parse_event({"cmd": "DANMU_MSG", "info": []}, 5440) is None
    assert parse_danmu_message({"cmd": "SEND_GIFT"}) is None


def test_is_mirror_accepts_cmd_payload_and_string() -> None:
    assert is_mirror("DANMU_MSG_MIRROR") is True
    assert is_mirror("DANMU_MSG") is False
    assert is_mirror({"cmd": "SEND_GIFT_MIRROR"}) is True
    assert is_mirror({"cmd": "SEND_GIFT", "data": {"is_mirror": True}}) is True
    assert is_mirror({"cmd": "SEND_GIFT", "data": {}}) is False
    assert is_mirror(None) is False


def test_parse_gift_json_fields() -> None:
    payload = {
        "cmd": "SEND_GIFT",
        "data": {
            "uid": 8,
            "uname": "观众",
            "giftName": "辣条",
            "num": 3,
            "total_coin": 300,
            "price": 100,
            "coin_type": "gold",
            "rnd": "r1",
            "tid": "t1",
            "guard_level": 3,
            "timestamp": 1700000000,
        },
    }
    event = parse_event(payload, 5440)
    assert event is not None
    assert (event.kind, event.room_id, event.uid, event.name, event.text, event.value, event.ts) == (
        "gift",
        5440,
        8,
        "观众",
        "辣条",
        300,
        1700000000,
    )
    assert event.raw is payload
    assert event_key(event) == "gift:5440:8:t1"


def test_parse_super_chat_guard_toast_and_delete() -> None:
    sc = {
        "cmd": "SUPER_CHAT_MESSAGE",
        "data": {
            "uid": 9,
            "price": 30,
            "message": "加油",
            "id": 100,
            "start_time": 1700000001,
            "user_info": {"uname": "老板"},
            "gift": {"gift_id": 12000, "gift_name": "醒目留言"},
        },
    }
    event = parse_event(sc, 5440)
    assert event is not None
    assert (event.kind, event.uid, event.name, event.text, event.value, event.ts) == (
        "super_chat",
        9,
        "老板",
        "加油",
        30,
        1700000001,
    )
    assert event_key(event) == "sc:5440:100"

    delete = parse_event({"cmd": "SUPER_CHAT_MESSAGE_DELETE", "data": {"ids": [100, 101]}}, 5440)
    assert delete is not None
    assert (delete.kind, delete.text, delete.value) == ("super_chat_delete", "100,101", 100)

    guard = parse_event(
        {
            "cmd": "GUARD_BUY",
            "data": {
                "uid": 10,
                "username": "舰长",
                "guard_level": 3,
                "num": 1,
                "price": 198000,
                "gift_name": "舰长",
                "start_time": 1700000002,
                "end_time": 1700000002,
            },
        },
        5440,
    )
    assert guard is not None
    assert (guard.kind, guard.name, guard.text, guard.value, guard.ts) == (
        "guard",
        "舰长",
        "舰长",
        198000,
        1700000002,
    )
    assert event_key(guard) == "guard:5440:10:3:1700000002"

    toast = parse_event(
        {
            "cmd": "USER_TOAST_MSG_V2",
            "data": {
                "sender_uinfo": {"uid": 10, "base": {"name": "舰长"}},
                "guard_info": {"guard_level": 3, "start_time": 1700000002},
                "pay_info": {"price": 198000, "num": 1, "unit": "月"},
                "gift_info": {"gift_id": 10003},
                "option": {"source": 0},
                "toast_msg": "开通了舰长",
            },
        },
        5440,
    )
    assert toast is not None
    assert (toast.kind, toast.uid, toast.name, toast.text, toast.value, toast.ts) == (
        "guard",
        10,
        "舰长",
        "开通了舰长",
        198000,
        1700000002,
    )
    assert event_key(toast) == event_key(guard)


def test_parse_room_lifecycle_events_and_unknown() -> None:
    live = parse_event({"cmd": "LIVE", "data": {"live_time": "1700000000"}}, 5440)
    assert live is not None and (live.kind, live.text) == ("live_start", "1700000000")
    assert parse_event({"cmd": "PREPARING"}, 5440).kind == "live_end"  # type: ignore[union-attr]

    watched = parse_event({"cmd": "WATCHED_CHANGE", "data": {"num": 12, "text_small": "12人看过"}}, 5440)
    assert watched is not None and (watched.kind, watched.value, watched.text) == (
        "watched_change",
        12,
        "12人看过",
    )

    entry = parse_event(
        {"cmd": "ENTRY_EFFECT", "data": {"uid": 11, "uinfo": {"base": {"name": "大佬"}}, "copy_writing": "来了"}},
        5440,
    )
    assert entry is not None and (entry.kind, entry.uid, entry.name, entry.text) == (
        "entry_effect",
        11,
        "大佬",
        "来了",
    )

    assert parse_event({"cmd": "SOMETHING_NEW", "data": {}}, 5440) is None
    assert parse_event({"data": {}}, 5440) is None
    assert parse_event("not-json", 5440) is None
    assert parse_events({"cmd": "SOMETHING_NEW"}) == []


def test_parse_gift_v2_protobuf_batch_and_fallback() -> None:
    gifts = [
        SendGiftV2GiftItem(gift_name="辣条", num=2, total_coin=200, tid="t1", rnd="r1", timestamp=1700000000),
        SendGiftV2GiftItem(gift_name="小花花", num=1, total_coin=100, tid="t2", timestamp=1700000001),
    ]
    broadcast = SendGiftBroadcast(uid=8, uname="观众", guard_level=3, gift_list=gifts)
    payload = {
        "cmd": "SEND_GIFT_V2",
        "data": {"pb": base64.b64encode(broadcast.dumps()).decode("ascii")},
    }
    events = parse_events(payload, 5440)
    assert [event.kind for event in events] == ["gift", "gift"]
    assert [(event.uid, event.name, event.text, event.value, event.ts) for event in events] == [
        (8, "观众", "辣条", 200, 1700000000),
        (8, "观众", "小花花", 100, 1700000001),
    ]
    assert event_key(events[0]) == "gift:5440:8:t1"

    assert parse_event(payload, 5440).text == "辣条"  # type: ignore[union-attr]
    assert parse_events({"cmd": "SEND_GIFT_V2", "data": {"pb": "not-base64"}}, 5440) == []
    assert parse_events({"cmd": "SEND_GIFT_V2", "data": {}}, 5440) == []


def test_parse_interact_word_v2_msg_types() -> None:
    for msg_type, kind in ((1, "enter"), (2, "follow"), (3, "share"), (6, "like")):
        proto = InteractWordV2(uid=9, uname="新人", msg_type=msg_type, timestamp=1700000000)
        payload = {"cmd": "INTERACT_WORD_V2", "data": {"pb": base64.b64encode(proto.dumps()).decode("ascii")}}
        event = parse_event(payload, 5440)
        assert event is not None
        assert (event.kind, event.uid, event.name, event.ts) == (kind, 9, "新人", 1700000000)
    assert parse_events({"cmd": "INTERACT_WORD_V2", "data": {"pb": "bad"}}, 5440) == []
