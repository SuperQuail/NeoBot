"""官方事件映射：openid 直通的 C2C/群消息、权威 @ 标记、通知、附件、引用、去重与 RFC3339 时间。"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from neobot_contracts.ports.logging import NullLogger

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.official.events import EventMapper
from neobot_adapter.official.identity import MessageIdMap
from neobot_adapter.utils.parse import safe_parse_model


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _RecordingLogger(NullLogger):
    """捕获结构化日志字段，供 @ 判定诊断断言使用。"""

    def __init__(self) -> None:
        self.debugs: list[tuple[str, dict]] = []
        self.infos: list[tuple[str, dict]] = []
        self.warnings: list[tuple[str, dict]] = []

    def bind(self, **ctx: object) -> "_RecordingLogger":
        return self

    def debug(self, msg: str, **kw: object) -> None:
        self.debugs.append((msg, kw))

    def info(self, msg: str, **kw: object) -> None:
        self.infos.append((msg, kw))

    def warning(self, msg: str, **kw: object) -> None:
        self.warnings.append((msg, kw))


def _mapper(_workdir, *, self_id: int = 1020304) -> EventMapper:
    return EventMapper(
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
    assert event["user_id"] == "user-openid-1"
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
    assert event["group_id"] == "group-openid-1"
    assert event["user_id"] == "member-openid-1"
    assert event["sender"]["role"] == "member"
    assert event["message"][0] == {"type": "at", "data": {"qq": 1020304}}
    assert event["message"][1] == {"type": "text", "data": {"text": " 在吗"}}
    assert event["mentioned_self"] is True


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
        "data": {"qq": str("member-openid-2"), "name": "小明"},
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
        str(segment.get("data", {}).get("text") or "") for segment in event["message"] if segment["type"] == "text"
    )
    assert text.split() == ["/linkqq", "3514733681"]


def test_full_group_message_with_bot_marker_gets_bot_at(workdir) -> None:
    """群全量消息 content 里的 @bot 标记要权威判为被 @，并保留 at 段给文本渲染。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "BOTOPENID"

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
    assert event["mentioned_self"] is True
    assert {"type": "at", "data": {"qq": 1020304}} in event["message"]
    text = "".join(
        str(segment.get("data", {}).get("text") or "") for segment in event["message"] if segment["type"] == "text"
    )
    assert text.split() == ["/linkqq", "3514733681"]


def test_user_group_at_example_is_authoritative_mention(workdir) -> None:
    """用户给的 GROUP_AT 示例：content 已去掉 @ 前缀、没有 mentions，事件类型即权威 @。"""
    mapper = _mapper(workdir)
    payload = _dispatch(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": "ROBOT1.0_user-example",
            "content": " /今日天气 ",
            "timestamp": "2026-11-12T12:00:00+08:00",
            "group_openid": "group-openid-1",
            "author": {
                "id": "member-openid-1",
                "member_openid": "member-openid-1",
                "union_openid": "union-openid-1",
            },
            "message_scene": {"source": "default", "ext": []},
        },
    )

    event = mapper.from_dispatch(payload)

    assert event is not None
    assert event["mentioned_self"] is True
    assert " /今日天气 " in event["raw_message"]


def test_full_group_message_without_mention_is_false(workdir) -> None:
    """群全量消息没有 @ 机器人时，权威结论是 False，不是「未知」。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(_dispatch("GROUP_MESSAGE_CREATE", _group_data(content="随便聊聊")))

    assert event is not None
    assert event["message"] == [{"type": "text", "data": {"text": "随便聊聊"}}]
    assert event["mentioned_self"] is False


def test_full_group_message_content_marker_mentions_bot(workdir) -> None:
    mapper = _mapper(workdir)
    mapper.bot_openid = "BOTOPENID"

    event = mapper.from_dispatch(
        _dispatch("GROUP_MESSAGE_CREATE", _group_data(content="<@!BOTOPENID> /help"))
    )

    assert event is not None
    assert event["mentioned_self"] is True
    assert {"type": "at", "data": {"qq": 1020304}} in event["message"]


def test_full_group_message_content_marker_for_other_user_is_false(workdir) -> None:
    mapper = _mapper(workdir)
    mapper.bot_openid = "BOTOPENID"

    event = mapper.from_dispatch(
        _dispatch("GROUP_MESSAGE_CREATE", _group_data(content="<@!OTHEROPENID> 你看"))
    )

    assert event is not None
    assert event["mentioned_self"] is False


def test_full_group_message_mentions_entry_for_bot_is_true(workdir) -> None:
    """正文没有标记时，mentions 里 bot=true 且 openid 命中也算被 @。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="/help",
                mentions=[
                    {"id": "bot-openid", "username": "机器人", "bot": True},
                    {"id": "member-openid-2", "username": "小明", "bot": False},
                ],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is True


def test_full_group_message_mentions_other_bot_is_false(workdir) -> None:
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(content="/help", mentions=[{"id": "other-bot-openid", "bot": True}]),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False


def test_full_group_message_msg_elements_entry_for_bot_is_true(workdir) -> None:
    """msg_elements 里的结构化 bot 条目同样可以权威判定。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(content="/help", msg_elements=[{"id": "bot-openid", "bot": True}]),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is True


def test_full_group_message_without_bot_openid_is_false_and_warns_once(workdir) -> None:
    """READY 没给出机器人 openid 且没有 mention 证据时：False，且只告警一次。"""
    logger = _RecordingLogger()
    mapper = EventMapper(message_ids=MessageIdMap(), logger=logger, self_id=1020304)

    first = mapper.from_dispatch(
        _dispatch("GROUP_MESSAGE_CREATE", _group_data(content="<@!UNKNOWNBOT> 在吗"), event_id="evt-1")
    )
    second = mapper.from_dispatch(
        _dispatch("GROUP_MESSAGE_CREATE", _group_data(content="又一条"), event_id="evt-2")
    )

    assert first is not None and first["mentioned_self"] is False
    assert second is not None and second["mentioned_self"] is False
    warnings = [msg for msg, _kw in logger.warnings if "openid" in msg]
    assert len(warnings) == 1
    assert "无法判定" in warnings[0]


# 线上真实形态（2026-11-12 15:27）：READY 的 d.user.id 与群场景 member_openid 不同，
# content 的 @ 标记和 mentions 的 bot=true 条目都用群场景 id。
_REAL_BOT_OPENID = "3380288042268959343"
_REAL_GROUP_SCENE_BOT_ID = "9B219BEA924B74503313310AD80A308D"


def test_full_group_message_group_scene_bot_mention_is_true(workdir) -> None:
    """READY openid 对不上群场景 member_openid 时，按正文标记 + bot mention 兜底判 @。"""
    logger = _RecordingLogger()
    mapper = EventMapper(message_ids=MessageIdMap(), logger=logger, self_id=0)
    mapper.bot_openid = _REAL_BOT_OPENID
    mentions = [{"id": _REAL_GROUP_SCENE_BOT_ID, "username": "NeoBot", "bot": True}]

    first = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(content=f"<@!{_REAL_GROUP_SCENE_BOT_ID}> /help", mentions=mentions),
            event_id="evt-real-1",
        )
    )
    second = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(content=f"<@!{_REAL_GROUP_SCENE_BOT_ID}> /help", mentions=mentions),
            event_id="evt-real-2",
        )
    )

    assert first is not None and first["mentioned_self"] is True
    assert second is not None and second["mentioned_self"] is True
    fields = next(kw for _msg, kw in logger.infos if kw.get("mentioned_self") is True)
    assert fields["source"] == "bot_mention"
    assert fields["content_at_ids"] == [_REAL_GROUP_SCENE_BOT_ID]
    assert fields["bot_mention_ids"] == [_REAL_GROUP_SCENE_BOT_ID]
    assert fields["bot_mention_names"] == ["NeoBot"]
    # 兜底判定不再单独打 warning（_log_addressing 的诊断日志已覆盖此信息）。
    assert not [msg for msg, _kw in logger.warnings if "群场景" in msg]


def test_full_group_message_bot_mention_matched_by_username(workdir) -> None:
    """机器人昵称已知时优先按 mention.username 认定，不依赖标记位置。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = _REAL_BOT_OPENID
    mapper.bot_username = "NeoBot"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content=f"/help <@!{_REAL_GROUP_SCENE_BOT_ID}>",
                mentions=[{"id": _REAL_GROUP_SCENE_BOT_ID, "username": "NeoBot", "bot": True}],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is True


def test_full_group_message_other_bot_marker_not_matching_mention_is_false(workdir) -> None:
    """正文 @ 的 id 与 mentions 里的 bot=true 条目对不上：不得误判成 @ 机器人。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = _REAL_BOT_OPENID

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="<@!OTHERBOTID> /help",
                mentions=[{"id": _REAL_GROUP_SCENE_BOT_ID, "username": "NeoBot", "bot": True}],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False


def test_full_group_message_other_bot_with_username_vetoes_fallback(workdir) -> None:
    """昵称已知且 mentions 里是别的 bot 昵称：即使 @ 标记在开头也不得判成本机器人。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = _REAL_BOT_OPENID
    mapper.bot_username = "NeoBot"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="<@!OTHER-BOT-ID> /help",
                mentions=[{"id": "OTHER-BOT-ID", "bot": True, "username": "OtherBot"}],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False


def test_full_group_message_known_username_but_mention_name_missing_keeps_fallback(workdir) -> None:
    """昵称已知但 mention 没给 username：保持谨慎的位置兜底现状。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = _REAL_BOT_OPENID
    mapper.bot_username = "NeoBot"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content=f"<@!{_REAL_GROUP_SCENE_BOT_ID}> /help",
                mentions=[{"id": _REAL_GROUP_SCENE_BOT_ID, "bot": True}],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is True


def test_addressing_log_plain_user_mention_is_debug(workdir) -> None:
    """普通群友 @（只有 content_at_ids，没有 bot 信号）只记 DEBUG，避免活跃群刷屏。"""
    logger = _RecordingLogger()
    mapper = EventMapper(message_ids=MessageIdMap(), logger=logger, self_id=1020304)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="<@!member-openid-9> 你看",
                mentions=[{"id": "member-openid-9", "bot": False}],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False
    assert not [kw for _msg, kw in logger.infos if "mentioned_self" in kw]
    fields = next(kw for _msg, kw in logger.debugs if "mentioned_self" in kw)
    assert fields["content_at_ids"] == ["member-openid-9"]
    assert fields["mentioned_self"] is False


def test_addressing_log_bot_mention_signal_is_info(workdir) -> None:
    """mentions 里出现 bot=true（真正的 bot 信号）时即使未被 @ 也记 INFO。"""
    logger = _RecordingLogger()
    mapper = EventMapper(message_ids=MessageIdMap(), logger=logger, self_id=1020304)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(content="随便聊聊", mentions=[{"id": "other-bot-openid", "bot": True}]),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False
    fields = next(kw for _msg, kw in logger.infos if "mentioned_self" in kw)
    assert fields["bot_mention_ids"] == ["other-bot-openid"]
    assert fields["mentioned_self"] is False


def test_full_group_message_bot_marker_not_at_start_with_other_mentions_is_false(workdir) -> None:
    """bot 标记不在开头且正文还有别的 @：证据不足时不兜底（宁漏判不误判）。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = _REAL_BOT_OPENID

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content=f"<@!member-openid-2> 你看 <@!{_REAL_GROUP_SCENE_BOT_ID}>",
                mentions=[
                    {"id": "member-openid-2", "username": "小明", "bot": False},
                    {"id": _REAL_GROUP_SCENE_BOT_ID, "username": "NeoBot", "bot": True},
                ],
            ),
        )
    )

    assert event is not None
    assert event["mentioned_self"] is False


def test_quoted_message_msg_elements_do_not_count_as_mention(workdir) -> None:
    """引用消息（message_type=103）的 msg_elements 是原消息，不能当本条 @ 来源。"""
    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MESSAGE_CREATE",
            _group_data(
                content="/help",
                message_type=103,
                msg_elements=[{"id": "bot-openid", "username": "机器人", "bot": True}],
            ),
        )
    )

    assert event is not None
    assert event["message"] == [{"type": "text", "data": {"text": "/help"}}]
    assert event["mentioned_self"] is False


def test_group_at_event_is_authoritative_without_robot_uin(workdir) -> None:
    """机器人 uin 未解析（self_id=0）时，GROUP_AT 事件仍权威判定为被 @。"""
    mapper = _mapper(workdir, self_id=0)

    event = mapper.from_dispatch(_dispatch("GROUP_AT_MESSAGE_CREATE", _group_data(content=" /今日天气 ")))

    assert event is not None
    assert event["mentioned_self"] is True
    assert event["message"][0] == {"type": "at", "data": {"qq": 0}}


def test_group_at_mapping_logs_addressing_diagnostics(workdir) -> None:
    """映射时输出固定字段诊断，便于定位「没反应」发生在哪一步。"""
    logger = _RecordingLogger()
    mapper = EventMapper(message_ids=MessageIdMap(), logger=logger, self_id=1020304)

    event = mapper.from_dispatch(_dispatch("GROUP_AT_MESSAGE_CREATE", _group_data(content=" /今日天气 ")))

    assert event is not None
    fields = next(kw for _msg, kw in logger.infos if "mentioned_self" in kw)
    assert fields["event_type"] == "GROUP_AT_MESSAGE_CREATE"
    assert fields["message_id"] == event["message_id"]
    assert fields["group_openid"] == "group-openid-1"
    assert fields["sender_id"] == "member-openid-1"
    assert fields["mentioned_self"] is True
    assert fields["source"] == "event_type"
    assert fields["self_id"] == 1020304
    assert "bot_openid" in fields


def test_group_message_model_carries_mentioned_self_only(workdir) -> None:
    """官方权威标记只加在群消息模型上；旧的 official_at 字段已删除。"""
    assert "mentioned_self" in GroupMessage.model_fields
    assert "mentioned_self" not in PrivateMessage.model_fields
    assert "official_at" not in GroupMessage.model_fields

    mapper = _mapper(workdir)
    mapper.bot_openid = "bot-openid"
    event = mapper.from_dispatch(_dispatch("GROUP_MESSAGE_CREATE", _group_data(content="随便聊聊")))
    assert event is not None
    assert safe_parse_model(event, GroupMessage).mentioned_self is False


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


def test_member_role_is_passed_through(workdir) -> None:
    mapper = _mapper(workdir)

    admin_event = mapper.map_message(
        "GROUP_MESSAGE_CREATE",
        _group_data(author={"member_openid": "m1", "username": "管理员", "member_role": "admin"}),
    )
    owner_event = mapper.map_message(
        "GROUP_MESSAGE_CREATE",
        _group_data(author={"member_openid": "m2", "username": "群主", "member_role": "owner"}),
    )
    unknown_event = mapper.map_message(
        "GROUP_MESSAGE_CREATE",
        _group_data(author={"member_openid": "m3", "username": "路人", "member_role": "weird"}),
    )

    assert admin_event is not None and admin_event["sender"]["role"] == "admin"
    assert owner_event is not None and owner_event["sender"]["role"] == "owner"
    assert unknown_event is not None and unknown_event["sender"]["role"] == "member"


def test_voice_wav_url_maps_to_record_segment(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "C2C_MESSAGE_CREATE",
            _c2c_data(
                content="",
                attachments=[
                    {
                        "content_type": "voice",
                        "voice_wav_url": "https://x/voice.wav",
                        "asr_refer_text": "语音转出来的文字",
                    }
                ],
            ),
        )
    )

    assert event is not None
    assert {"type": "record", "data": {"file": "https://x/voice.wav", "url": "https://x/voice.wav"}} in event["message"]
    texts = [segment["data"]["text"] for segment in event["message"] if segment["type"] == "text"]
    assert "语音转出来的文字" in texts


def test_message_scene_msg_idx_is_remembered_for_reply_reference(workdir) -> None:
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "C2C_MESSAGE_CREATE",
            _c2c_data(message_scene={"source": "default", "ext": ["msg_idx=REFIDX_incoming=="]}),
        )
    )

    assert event is not None
    synthetic = event["message_id"]
    assert mapper._message_ids.reference(synthetic) == "REFIDX_incoming=="
    context = mapper._message_ids.context(synthetic)
    assert context is not None
    assert context["kind"] == "private"
    assert context["openid"] == "user-openid-1"


def test_group_member_add_maps_to_notice(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_MEMBER_ADD",
            {"timestamp": 1784276757, "group_openid": "group-openid-1", "member_openid": "member-openid-2"},
        )
    )
    assert event is not None
    assert event["post_type"] == "notice"
    assert event["notice_type"] == "group_increase"
    assert event["group_id"] == "group-openid-1"
    assert event["user_id"] == "member-openid-2"


def test_group_join_request_maps_to_request(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_JOIN_REQUEST",
            {
                "group_openid": "group-openid-1",
                "join_request_id": "req-1",
                "member_openid": "member-openid-3",
                "username": "申请人",
                "apply_at": "2026-08-05T16:21:40+08:00",
                "verify_info": {"method": "verify_message", "verify_message": "放我进去"},
            },
        )
    )
    assert event is not None
    assert event["post_type"] == "request"
    assert event["request_type"] == "group"
    assert event["flag"] == "req-1"
    assert event["comment"] == "放我进去"
    assert event["_official_member_openid"] == "member-openid-3"


def test_friend_add_maps_to_notice(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch("FRIEND_ADD", {"timestamp": 1784570523, "openid": "user-openid-9", "scene": 1001})
    )
    assert event is not None
    assert event["notice_type"] == "friend_add"
    assert event["user_id"] == "user-openid-9"


def test_group_msg_receive_maps_to_notice(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch("GROUP_MSG_RECEIVE", {"timestamp": 1784276800, "group_openid": "group-openid-1"})
    )
    assert event is not None
    assert event["notice_type"] == "group_msg_receive"
    assert event["group_id"] == "group-openid-1"


def test_c2c_msg_reject_maps_to_notice(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch("C2C_MSG_REJECT", {"timestamp": 1784570599, "openid": "user-openid-1"})
    )
    assert event is not None
    assert event["notice_type"] == "c2c_msg_reject"
    assert event["user_id"] == "user-openid-1"


def test_subscribe_message_status_maps_to_notice(workdir) -> None:
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch(
            "SUBSCRIBE_MESSAGE_STATUS",
            {"openid": "user-openid-1", "result": [{"template_id": 1, "op": 1}]},
        )
    )
    assert event is not None
    assert event["notice_type"] == "subscribe_message_status"
    assert event["subscribe_results"] == [{"template_id": 1, "op": 1}]


def test_group_at_event_without_mentions_keeps_explicit_at_target(workdir) -> None:
    """GROUP_AT_MESSAGE_CREATE 只带正文 @ 标记、没有 mentions 时也要保留 at 段。"""
    mapper = _mapper(workdir)

    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_AT_MESSAGE_CREATE",
            _group_data(content="<@!BOTOPENID> /linkqq <@!member-openid-2> 3514733681"),
        )
    )

    assert event is not None
    at_ids = [
        str(segment["data"].get("qq"))
        for segment in event["message"]
        if segment["type"] == "at"
    ]
    assert "member-openid-2" in at_ids


def test_group_at_event_without_bot_prefix_keeps_first_mention(workdir) -> None:
    """实测：平台常去掉 @机器人 前缀，content 以 /linkqq <@!目标> 开头。"""
    mapper = _mapper(workdir)
    event = mapper.from_dispatch(
        _dispatch(
            "GROUP_AT_MESSAGE_CREATE",
            _group_data(content="/linkqq <@!member-openid-2> 3789029663"),
        )
    )
    assert event is not None
    at_ids = [str(s["data"].get("qq")) for s in event["message"] if s["type"] == "at"]
    assert "member-openid-2" in at_ids


def test_at_event_is_marked_official_at_event(workdir) -> None:
    mapper = _mapper(workdir)
    mapper.bot_openid = "BOTOPENID"
    at_event = mapper.from_dispatch(_dispatch("GROUP_AT_MESSAGE_CREATE", _group_data(content="<@!BOTOPENID> /help")))
    full_event = mapper.from_dispatch(_dispatch("GROUP_MESSAGE_CREATE", _group_data(id="ROBOT1.0_full-msg", content="<@!BOTOPENID> /help"), event_id="evt-2"))
    assert at_event is not None and at_event["official_at_event"] is True
    assert full_event is not None and full_event["official_at_event"] is False

