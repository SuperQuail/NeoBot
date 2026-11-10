"""官方事件映射：C2C/群 @ 消息、附件、引用、去重与 RFC3339 时间。"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from neobot_contracts.ports.logging import NullLogger

from neobot_adapter.official.events import EventMapper
from neobot_adapter.official.identity import IdentityMap, MessageIdMap


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _mapper(workdir, *, self_id: int = 1020304) -> EventMapper:
    return EventMapper(
        identity=IdentityMap(workdir),
        message_ids=MessageIdMap(),
        logger=NullLogger(),
        self_id=self_id,
    )


def _dispatch(event_type: str, data: dict, *, event_id: str = "evt-1") -> dict:
    return {"op": 0, "t": event_type, "id": event_id, "s": 1, "d": data}


def _c2c_data(**overrides) -> dict:
    data = {
        "id": "ROBOT1.0_c2c-msg",
        "content": "你好",
        "timestamp": "2026-01-02T03:04:05+08:00",
        "author": {"user_openid": "user-openid-1", "username": "Alice"},
    }
    data.update(overrides)
    return data


def _group_data(**overrides) -> dict:
    data = {
        "id": "ROBOT1.0_group-msg",
        "content": "在吗",
        "timestamp": "2026-01-02T03:04:05+08:00",
        "group_openid": "group-openid-1",
        "author": {"member_openid": "member-openid-1", "username": "Bob"},
    }
    data.update(overrides)
    return data


def test_c2c_message_maps_to_private_event(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(_dispatch("C2C_MESSAGE_CREATE", _c2c_data()))

    assert event is not None
    assert event["post_type"] == "message"
    assert event["message_type"] == "private"
    assert event["sub_type"] == "friend"
    assert event["self_id"] == 1020304
    assert event["target_id"] == 1020304
    assert event["_official_message_id"] == "ROBOT1.0_c2c-msg"
    assert event["message_id"] > 0
    assert event["user_id"] == mapper._identity.user_id("user-openid-1")
    assert event["sender"]["nickname"] == "Alice"
    assert event["message"] == [{"type": "text", "data": {"text": "你好"}}]
    expected_time = int(datetime.fromisoformat("2026-01-02T03:04:05+08:00").timestamp())
    assert event["time"] == expected_time


def test_group_at_message_puts_at_segment_first(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_AT_MESSAGE_CREATE",
            _group_data(content="<@!BOTOPENID> 在吗"),
        )
    )

    assert event is not None
    assert event["message_type"] == "group"
    assert event["group_id"] == mapper._identity.group_id("group-openid-1")
    assert event["user_id"] == mapper._identity.user_id("member-openid-1")
    assert event["sender"]["role"] == "member"
    assert event["message"][0] == {"type": "at", "data": {"qq": 1020304}}
    assert event["message"][1] == {"type": "text", "data": {"text": " 在吗"}}


def test_group_mentions_become_at_segments(workdir) -> None:
    """官方 mentions 是「被 @ 的其他用户」；不转 at 段命令层就拿不到被 @ 者。"""
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_AT_MESSAGE_CREATE",
            _group_data(
                content="<@!BOTOPENID> 你们看这个 <@!member-openid-2>",
                mentions=[
                    {"id": "member-openid-2", "username": "小明", "bot": False},
                    {"id": "bot-openid", "username": "另一个机器人", "bot": True},
                ],
            ),
        )
    )

    assert event is not None
    segments = event["message"]
    assert segments[0] == {"type": "at", "data": {"qq": 1020304}}
    # 顺序与真实消息一致：@ 在正文后面就排在正文后面
    assert segments[1] == {"type": "text", "data": {"text": " 你们看这个 "}}
    assert segments[2] == {
        "type": "at",
        "data": {"qq": str(mapper._identity.user_id("member-openid-2")), "name": "小明"},
    }
    assert all(segment.get("data", {}).get("name") != "另一个机器人" for segment in segments)


def test_mention_inside_command_keeps_token_spaces(workdir) -> None:
    """中文 @ 标记夹在命令参数之间时，text 段拼接后必须仍能 split 出命令和参数。"""
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_AT_MESSAGE_CREATE",
            _group_data(
                content="<@!BOTOPENID> /linkqq <@!member-openid-2> 3514733681",
                mentions=[{"id": "member-openid-2", "username": "枫", "bot": False}],
            ),
        )
    )

    assert event is not None
    types = [segment["type"] for segment in event["message"]]
    assert types == ["at", "text", "at", "text"]
    text = "".join(
        str(segment.get("data", {}).get("text") or "")
        for segment in event["message"]
        if segment["type"] == "text"
    )
    assert text.split() == ["/linkqq", "3514733681"]


def test_full_group_message_with_bot_marker_gets_bot_at(workdir) -> None:
    """群全量消息 content 里的 @bot 标记也要转成 at 段，否则命令管线无法触发。"""
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="<@!BOTOPENID> /linkqq <@!member-openid-2> 3514733681",
                mentions=[{"id": "member-openid-2", "username": "枫", "bot": False}],
            ),
        )
    )

    assert event is not None
    assert {"type": "at", "data": {"qq": 1020304}} in event["message"]
    text = "".join(
        str(segment.get("data", {}).get("text") or "")
        for segment in event["message"]
        if segment["type"] == "text"
    )
    assert text.split() == ["/linkqq", "3514733681"]


def test_group_plain_message_has_no_at_segment(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(_dispatch("GROUP_MESSAGE_CREATE", _group_data(content="随便聊聊")))

    assert event is not None
    assert event["message"] == [{"type": "text", "data": {"text": "随便聊聊"}}]


def test_image_attachment_maps_to_image_segment(workdir) -> None:
    mapper = _mapper(workdir)
    url = "https://multimedia.nt.qq.com.cn/a.png"

    event = mapper.from_dispatch(
        _dispatch(
            "C2C_MESSAGE_CREATE",
            _c2c_data(
                content="",
                attachments=[{"content_type": "image/png", "url": url}],
            ),
        )
    )

    assert event is not None
    assert {"type": "image", "data": {"file": url, "url": url}} in event["message"]


def test_voice_uses_asr_text_or_placeholder(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "C2C_MESSAGE_CREATE",
            _c2c_data(
                content="",
                attachments=[
                    {
                        "content_type": "voice/silk",
                        "url": "https://x/1.silk",
                        "asr_refer_text": "语音转出来的文字",
                    },
                    {"content_type": "voice/silk", "url": "https://x/2.silk"},
                ],
            ),
        )
    )

    assert event is not None
    texts = [segment["data"]["text"] for segment in event["message"] if segment["type"] == "text"]
    assert "语音转出来的文字" in texts
    assert "[语音消息]" in texts


def test_quoted_message_is_prepended_as_text(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "C2C_MESSAGE_CREATE",
            _c2c_data(
                content="回复内容",
                message_type=103,
                msg_elements=[{"content": "原消息"}],
            ),
        )
    )

    assert event is not None
    assert event["message"][0] == {
        "type": "text",
        "data": {"text": "[引用] 原消息\n"},
    }
    assert event["message"][1] == {"type": "text", "data": {"text": "回复内容"}}


def test_duplicate_event_id_is_dropped(workdir) -> None:
    mapper = _mapper(workdir)
    payload = _dispatch("C2C_MESSAGE_CREATE", _c2c_data())

    assert mapper.from_dispatch(payload) is not None
    assert mapper.from_dispatch(payload) is None


def test_non_message_dispatch_returns_none(workdir) -> None:
    mapper = _mapper(workdir)

    assert mapper.from_dispatch({"op": 0, "t": "READY", "d": {}}) is None


def test_same_official_id_reuses_synthetic_message_id(workdir) -> None:
    mapper = _mapper(workdir)
    data = _c2c_data()

    first = mapper.map_message("C2C_MESSAGE_CREATE", dict(data))
    second = mapper.map_message("C2C_MESSAGE_CREATE", dict(data))

    assert first is not None and second is not None
    assert first["message_id"] == second["message_id"]


def test_message_without_author_is_skipped(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(_dispatch("C2C_MESSAGE_CREATE", _c2c_data(author={})))

    assert event is None


def test_bot_mention_in_mentions_adds_bot_at_without_content_marker(workdir) -> None:
    """全量消息若剥掉了 content 里的 @bot，仍可从 mentions 的 bot=true 认出。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="/linkqq 3514733681",
                mentions=[
                    {"id": "bot-openid", "username": "机器人", "bot": True},
                    {"id": "other-bot-openid", "username": "别的机器人", "bot": True},
                ],
            ),
        )
    )

    assert event is not None
    assert {"type": "at", "data": {"qq": 1020304}} in event["message"]
    assert all(segment.get("data", {}).get("name") != "别的机器人" for segment in event["message"])
