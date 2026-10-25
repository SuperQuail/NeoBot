"""B站跨聊天通道 + CrossChatSkill.bilibili 目标测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.bilibili.channel import BilibiliCrossChatChannel, parse_conversation_id
from neobot_app.skills.cross_chat_skill import CrossChatSkill


class FakeEngine:
    def __init__(self, reply: str | None = "收到", *, available: bool = True) -> None:
        self.reply = reply
        self.available = available
        self.calls: list[tuple[str, str]] = []

    async def generate_task_reply(self, task, *, history="", live=False):
        self.calls.append((task, history))
        return self.reply


class FakeClient:
    my_uid = 999

    def __init__(self, *, fail_send: bool = False) -> None:
        self.fail_send = fail_send
        self.messages = [
            SimpleNamespace(sender_uid=55, text="在吗", timestamp=100, is_self=False),
            SimpleNamespace(sender_uid=999, text="在的", timestamp=101, is_self=True),
        ]
        self.comments = [
            {
                "member": {"uname": "张三"},
                "content": {"message": "视频不错"},
            }
        ]
        self.sent_messages: list[tuple[int, str]] = []
        self.sent_comments: list[dict] = []
        #: 历史读取时实际用的 (oid, comment_type)
        self.comment_calls: list[tuple[int, int]] = []

    def get_messages(self, talker_id, size=5):
        return self.messages

    def get_comments(self, oid, comment_type=1, *, mode="hot", cursor=None, page_size=20):
        self.comment_calls.append((oid, comment_type))
        return {"items": self.comments, "cursor": "", "is_end": True, "raw": {}}

    def send_message(self, receiver_id, text):
        if self.fail_send:
            return False
        self.sent_messages.append((receiver_id, text))
        return True

    def send_comment_reply(self, oid, root, parent, text, *, type_=1):
        if self.fail_send:
            return False
        self.sent_comments.append(
            {"oid": oid, "root": root, "parent": parent, "text": text, "type_": type_}
        )
        return True


class FakeHub:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, **kwargs):
        self.published.append(kwargs)


def test_parse_conversation_id_private() -> None:
    assert parse_conversation_id("private:55") == {"kind": "private", "uid": 55}


def test_parse_conversation_id_comment() -> None:
    target = parse_conversation_id("comment:10:20:30")

    assert target == {
        "kind": "comment",
        "type_": 1,
        "oid": 10,
        "root": 20,
        "parent": 30,
    }


def test_parse_conversation_id_invalid() -> None:
    assert parse_conversation_id("") is None
    assert parse_conversation_id("private:abc") is None
    assert parse_conversation_id("comment:1:2") is None
    assert parse_conversation_id("unknown:1:2:3") is None


async def test_channel_send_private_task() -> None:
    client = FakeClient()
    engine = FakeEngine("收到啦")
    channel = BilibiliCrossChatChannel(client, engine)

    ok, reply, detail = await channel.send_task("private:55", "告诉对方晚上开黑")

    assert ok is True
    assert reply == "收到啦"
    assert client.sent_messages == [(55, "收到啦")]
    assert engine.calls[0][0] == "告诉对方晚上开黑"
    assert "在吗" in engine.calls[0][1]  # 私信历史带进上下文


async def test_channel_send_comment_task() -> None:
    client = FakeClient()
    channel = BilibiliCrossChatChannel(client, FakeEngine("来了"))

    ok, reply, _ = await channel.send_task("dynamic:10:20:30", "回应一下")

    assert ok is True
    assert client.sent_comments == [
        {"oid": 10, "root": 20, "parent": 30, "text": "来了", "type_": 17}
    ]


async def test_channel_send_rejects_bad_conversation() -> None:
    channel = BilibiliCrossChatChannel(FakeClient(), FakeEngine())

    ok, _, detail = await channel.send_task("bad-id", "x")

    assert ok is False
    assert "格式" in detail


async def test_channel_send_without_client_or_engine() -> None:
    ok, _, detail = await BilibiliCrossChatChannel(None, FakeEngine()).send_task(
        "private:55", "x"
    )
    assert ok is False and "未登录" in detail

    ok, _, detail = await BilibiliCrossChatChannel(FakeClient(), None).send_task(
        "private:55", "x"
    )
    assert ok is False and "引擎" in detail


async def test_channel_dormant_service_reports_not_logged_in() -> None:
    """休眠服务（available=False）不回退成它的 client/service，按未登录处理。"""

    class DormantService:
        available = False

        def __init__(self, client: FakeClient) -> None:
            self.client = client

    client = FakeClient()
    channel = BilibiliCrossChatChannel(DormantService(client), FakeEngine())

    ok, reply, detail = await channel.send_task("private:55", "x")

    assert ok is False
    assert reply == ""
    assert "未登录" in detail
    assert client.sent_messages == []
    assert await channel.get_history("private:55") == ""


async def test_channel_skip_and_send_failure() -> None:
    channel = BilibiliCrossChatChannel(FakeClient(), FakeEngine(None))
    ok, _, detail = await channel.send_task("private:55", "x")
    assert ok is False and "不回应" in detail

    channel = BilibiliCrossChatChannel(FakeClient(fail_send=True), FakeEngine())
    ok, _, detail = await channel.send_task("private:55", "x")
    assert ok is False and "发送失败" in detail


async def test_channel_get_history_private_and_comment() -> None:
    channel = BilibiliCrossChatChannel(FakeClient(), FakeEngine())

    private = await channel.get_history("private:55")
    assert "在吗" in private and "你:在的" in private

    comment = await channel.get_history("comment:10:20:30")
    assert "张三" in comment and "视频不错" in comment


async def test_channel_history_uses_target_comment_type() -> None:
    """动态/专栏/opus 不能读视频评论区；opus 是 12（专栏）不是 11（番剧）。"""
    client = FakeClient()
    channel = BilibiliCrossChatChannel(client, FakeEngine())

    for conversation_id in ("dynamic:10:20:30", "opus:11:20:30", "article:12:20:30"):
        assert "视频不错" in await channel.get_history(conversation_id)

    assert client.comment_calls == [(10, 17), (11, 12), (12, 12)]


async def test_channel_send_opus_uses_article_type() -> None:
    client = FakeClient()
    channel = BilibiliCrossChatChannel(client, FakeEngine("来了"))

    ok, _, _ = await channel.send_task("opus:10:20:30", "回应一下")

    assert ok is True
    assert client.sent_comments[0]["type_"] == 12


async def test_channel_get_history_invalid_target() -> None:
    channel = BilibiliCrossChatChannel(FakeClient(), FakeEngine())

    assert await channel.get_history("bad-id") == ""


# ── CrossChatSkill 集成 ──


def _cross_chat(channel=None, hub=None) -> CrossChatSkill:
    return CrossChatSkill(bilibili_channel=channel, notification_hub=hub)


async def test_cross_chat_send_to_bilibili() -> None:
    client = FakeClient()
    skill = _cross_chat(BilibiliCrossChatChannel(client, FakeEngine("收到")))

    result = json.loads(
        await skill.execute(
            "cross_chat_send",
            {
                "target_kind": "bilibili",
                "target_id": "private:55",
                "task": "告诉对方晚上开黑",
            },
        )
    )

    assert result["ok"] is True
    assert result["status"] == "responded"
    assert result["reply"] == "收到"
    assert client.sent_messages == [(55, "收到")]


async def test_cross_chat_send_to_bilibili_with_response_relay() -> None:
    hub = FakeHub()
    skill = _cross_chat(
        BilibiliCrossChatChannel(FakeClient(), FakeEngine("收到")), hub
    )

    result = json.loads(
        await skill.execute(
            "cross_chat_send",
            {
                "target_kind": "bilibili",
                "target_id": "comment:10:20:30",
                "task": "回应一下",
                "notification_mode": "response",
                "pipeline_key": "group:123",
            },
        )
    )

    assert result["ok"] is True
    assert result["relayed"] is True
    assert hub.published[0]["kind"] == "group"
    assert hub.published[0]["conversation_id"] == "123"


async def test_cross_chat_send_without_bilibili_channel() -> None:
    skill = _cross_chat()

    result = json.loads(
        await skill.execute(
            "cross_chat_send",
            {"target_kind": "bilibili", "target_id": "private:55", "task": "x"},
        )
    )

    assert result["ok"] is False
    assert "未配置" in result["error"]


async def test_cross_chat_query_bilibili() -> None:
    skill = _cross_chat(BilibiliCrossChatChannel(FakeClient(), FakeEngine()))

    result = json.loads(
        await skill.execute(
            "cross_chat_query",
            {"target_kind": "bilibili", "target_id": "private:55"},
        )
    )

    assert result["ok"] is True
    assert "在吗" in result["history"]


async def test_cross_chat_query_without_bilibili_channel() -> None:
    skill = _cross_chat()

    result = json.loads(
        await skill.execute(
            "cross_chat_query",
            {"target_kind": "bilibili", "target_id": "private:55"},
        )
    )

    assert result["ok"] is False
    assert "未配置" in result["error"]


async def test_cross_chat_target_kind_validation_mentions_bilibili() -> None:
    skill = _cross_chat()

    result = json.loads(
        await skill.execute(
            "cross_chat_send",
            {"target_kind": "telegram", "target_id": "x", "task": "y"},
        )
    )

    assert result["ok"] is False
    assert "bilibili" in result["error"]


# ── 直播通道 ──


class FakeLive:
    def __init__(self, *, live: bool = True) -> None:
        self.live = live
        self.history = [
            {"uid": 8, "name": "观众甲", "text": "在吗", "time": "20:00:00"},
            {"uid": 9, "name": "观众乙", "text": "唱首歌", "time": "20:00:01"},
        ]
        self.sent: list[tuple[int, str]] = []
        self.live_calls: list[int] = []

    async def is_live(self, room_id: int) -> bool:
        self.live_calls.append(room_id)
        return self.live

    def get_history(self, room_id: int, count: int = 20) -> list[dict]:
        return self.history[-count:]

    async def send_danmaku(self, room_id: int, text: str) -> dict:
        if not self.live:
            return {"ok": False, "error": "未开播，不互动"}
        self.sent.append((room_id, text))
        return {"ok": True, "error": ""}


def test_parse_conversation_id_live() -> None:
    assert parse_conversation_id("live:5440") == {"kind": "live", "room_id": 5440}
    assert parse_conversation_id("live:0") is None
    assert parse_conversation_id("live:abc") is None


async def test_channel_live_send_and_history() -> None:
    live = FakeLive()
    engine = FakeEngine("来了")
    channel = BilibiliCrossChatChannel(None, engine, live)

    ok, reply, detail = await channel.send_task("live:5440", "跟观众打个招呼")

    assert ok is True
    assert reply == "来了"
    assert detail == "已发送到B站直播间"
    assert live.sent == [(5440, "来了")]
    assert live.live_calls == [5440]
    assert "在吗" in engine.calls[0][1]

    history = await channel.get_history("live:5440")
    assert "观众甲:在吗" in history
    assert "观众乙:唱首歌" in history


async def test_channel_live_offline_does_not_generate_or_send() -> None:
    live = FakeLive(live=False)
    engine = FakeEngine()
    channel = BilibiliCrossChatChannel(None, engine, live)

    ok, reply, detail = await channel.send_task("live:5440", "说点什么")

    assert ok is False
    assert reply == ""
    assert detail == "未开播，不互动"
    assert engine.calls == []
    assert live.sent == []


async def test_channel_live_missing_interactor() -> None:
    channel = BilibiliCrossChatChannel(FakeClient(), FakeEngine())

    ok, _, detail = await channel.send_task("live:5440", "x")

    assert ok is False
    assert "直播交互器" in detail
    assert await channel.get_history("live:5440") == ""
