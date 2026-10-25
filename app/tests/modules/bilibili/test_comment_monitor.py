"""BilibiliCommentMonitor 测试：默认关闭、去重、回复池、单轮上限、冷却、退避、@通知。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.bilibili.comment_monitor import (
    BilibiliCommentMonitor,
    CommentEvent,
    parse_feed_item,
)


class FakeEngine:
    def __init__(self, text: str | None = "好哦") -> None:
        self.text = text
        self.available = True
        self.contexts = []

    async def generate_comment_reply(self, ctx):
        self.contexts.append(ctx)
        return self.text


class FakeClient:
    my_uid = 999

    def __init__(
        self,
        feed=None,
        *,
        fail_feed: bool = False,
        fail_send: bool = False,
    ) -> None:
        self.feed = list(feed or [])
        self.fail_feed = fail_feed
        self.fail_send = fail_send
        self.sent: list[dict] = []

    def get_reply_feed(self, limit: int = 20):
        if self.fail_feed:
            raise RuntimeError("feed down")
        return self.feed

    def send_comment_reply(self, oid, root, parent, text, *, type_=1):
        if self.fail_send:
            return False
        self.sent.append(
            {"oid": oid, "root": root, "parent": parent, "text": text, "type_": type_}
        )
        return True


class FakeAtClient(FakeClient):
    def __init__(self, at_feed=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.at_feed = list(at_feed or [])

    def get_at_feed(self, limit: int = 20):
        return self.at_feed


def feed_item(
    notification_id: int = 1,
    *,
    oid: int = 10,
    parent: int = 100,
    root: int = 0,
    mid: int = 12,
    message: str = "你好",
    reply_time: int = 0,
    business_id: int = 1,
) -> dict:
    return {
        "id": notification_id,
        "reply_time": reply_time,
        "user": {"mid": mid, "nickname": "张三"},
        "item": {
            "subject_id": oid,
            "source_id": parent,
            "root_id": root,
            "business_id": business_id,
            "message": message,
            "title": "视频标题",
            "uri": "https://www.bilibili.com/video/BV1",
        },
    }


def at_feed_item(
    notification_id: int = 9,
    *,
    oid: int = 55,
    parent: int = 66,
    at_time: int = 1710000000,
    source_content: str = "这条评论 @了你",
) -> dict:
    """真实 /x/msgfeed/at 的字段形状：时间在 at_time、正文在 source_content。"""
    return {
        "id": notification_id,
        "at_time": at_time,
        "user": {"mid": 12, "nickname": "张三"},
        "item": {
            "subject_id": oid,
            "source_id": parent,
            "root_id": 0,
            "business_id": 1,
            "source_content": source_content,
            "content": "不应优先使用的正文",
            "title": "视频标题",
            "uri": "https://www.bilibili.com/video/BV1",
            "at_details": [{"mid": 999, "uname": "bot"}],
        },
    }


def _monitor(client, engine=None, **kwargs) -> BilibiliCommentMonitor:
    values = {
        "enabled": True,
        "poll_interval_seconds": 1800,
        "max_replies_per_poll": 3,
        "reply_cooldown_seconds": 0,
    }
    values.update(kwargs)
    return BilibiliCommentMonitor(client, engine or FakeEngine(), **values)


async def test_disabled_monitor_does_not_poll() -> None:
    client = FakeClient([feed_item()])
    engine = FakeEngine()
    monitor = BilibiliCommentMonitor(client, engine, enabled=False)

    assert await monitor.poll_once() == 0
    assert engine.contexts == []
    await monitor.start()
    assert monitor.is_running is False


async def test_new_reply_is_processed_and_sent() -> None:
    client = FakeClient([feed_item(notification_id=1, oid=10, parent=100, root=0)])
    engine = FakeEngine("好哦")
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 1
    assert client.sent[0]["oid"] == 10
    assert client.sent[0]["root"] == 100  # root_id=0 时 root=parent
    assert client.sent[0]["parent"] == 100
    assert client.sent[0]["text"] == "好哦"
    ctx = engine.contexts[0]
    assert ctx.comment_tree[0].uname == "张三"
    assert ctx.target_title == "视频标题"


async def test_duplicate_notification_is_skipped() -> None:
    client = FakeClient([feed_item(notification_id=1)])
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert await monitor.poll_once() == 0
    assert len(client.sent) == 1


async def test_own_comment_is_skipped() -> None:
    client = FakeClient([feed_item(notification_id=2, mid=FakeClient.my_uid)])
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert client.sent == []


async def test_old_notification_is_not_dropped_by_start_time() -> None:
    # 之前没回复的旧评论也进池回复，不再因早于监控启动时间被丢。
    client = FakeClient([feed_item(notification_id=1, reply_time=1)])
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert len(client.sent) == 1


async def test_max_replies_per_poll_queues_the_rest_for_next_poll() -> None:
    client = FakeClient(
        [feed_item(notification_id=i, oid=10 + i, parent=100 + i) for i in range(5)]
    )
    monitor = _monitor(client, max_replies_per_poll=2)

    assert await monitor.poll_once() == 2
    assert monitor.status()["pending"] == 3
    assert await monitor.poll_once() == 2
    assert monitor.status()["pending"] == 1
    assert await monitor.poll_once() == 1
    assert monitor.status()["pending"] == 0
    assert await monitor.poll_once() == 0
    assert len(client.sent) == 5


async def test_pending_pool_is_bounded() -> None:
    client = FakeClient(
        [feed_item(notification_id=i, oid=i, parent=i) for i in range(1, 1002)]
    )
    monitor = _monitor(client, max_replies_per_poll=1)

    assert await monitor.poll_once() == 1
    assert monitor.status()["pending"] == 999
    assert await monitor.poll_once() == 1
    assert monitor.status()["pending"] <= 1000
    assert len(client.sent) == 2


async def test_skip_from_engine_marks_processed_without_sending() -> None:
    client = FakeClient([feed_item(notification_id=1)])
    engine = FakeEngine(None)
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 0
    assert client.sent == []
    assert await monitor.poll_once() == 0
    assert len(engine.contexts) == 1


async def test_cooldown_blocks_same_thread() -> None:
    client = FakeClient(
        [
            feed_item(notification_id=1, oid=10, parent=100, root=100),
            feed_item(notification_id=2, oid=10, parent=101, root=100),
        ]
    )
    monitor = _monitor(client, reply_cooldown_seconds=600)

    assert await monitor.poll_once() == 1
    assert len(client.sent) == 1


async def test_send_failure_increases_backoff_and_retries_next_poll() -> None:
    client = FakeClient([feed_item(notification_id=1)], fail_send=True)
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert monitor.status()["pending"] == 1
    assert monitor.next_poll_interval == 3600

    client.fail_send = False
    assert await monitor.poll_once() == 1
    assert monitor.status()["pending"] == 0
    assert monitor.next_poll_interval == 1800


async def test_feed_failure_increases_backoff() -> None:
    client = FakeClient([], fail_feed=True)
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert monitor.next_poll_interval == 3600
    assert monitor.status()["failures"] == 1


async def test_at_feed_is_processed_when_client_supports_it() -> None:
    client = FakeAtClient(at_feed=[feed_item(notification_id=9, oid=55, parent=66)])
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert client.sent[0]["oid"] == 55


async def test_same_comment_in_reply_and_at_feed_is_replied_once() -> None:
    client = FakeAtClient(
        at_feed=[feed_item(notification_id=9, oid=55, parent=66)],
        feed=[feed_item(notification_id=1, oid=55, parent=66)],
    )
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert len(client.sent) == 1


async def test_async_client_methods_are_supported() -> None:
    class AsyncClient:
        my_uid = 999

        def __init__(self) -> None:
            self.sent = []

        async def get_reply_feed(self, limit=20):
            return [feed_item(notification_id=1)]

        async def send_comment_reply(self, oid, root, parent, text, *, type_=1):
            self.sent.append((oid, root, parent, text))
            return True

    client = AsyncClient()
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert client.sent == [(10, 100, 100, "好哦")]


async def test_poll_once_handles_dormant_client() -> None:
    monitor = _monitor(None)

    assert await monitor.poll_once() == 0


async def test_start_stop_lifecycle() -> None:
    client = FakeClient([feed_item(notification_id=1)])
    monitor = _monitor(client)

    await monitor.start()
    assert monitor.is_running is True
    await monitor.stop()
    assert monitor.is_running is False


def test_parse_feed_item_returns_none_for_incomplete() -> None:
    assert parse_feed_item({}) is None
    assert parse_feed_item({"item": {"subject_id": 1, "source_id": 0, "message": "x"}}) is None
    assert parse_feed_item({"item": {"subject_id": 1, "source_id": 2, "message": ""}}) is None


def test_default_poll_interval_is_1800() -> None:
    assert BilibiliCommentMonitor().next_poll_interval == 1800
    assert BilibiliCommentMonitor(poll_interval_seconds=0).next_poll_interval == 1800
    cfg = SimpleNamespace(bilibili=SimpleNamespace())
    assert BilibiliCommentMonitor.from_config(None, None, cfg).next_poll_interval == 1800


async def test_default_max_replies_per_poll_is_50() -> None:
    client = FakeClient(
        [feed_item(notification_id=i, oid=i, parent=i) for i in range(1, 61)]
    )
    monitor = BilibiliCommentMonitor(client, FakeEngine(), enabled=True)

    assert await monitor.poll_once() == 50
    assert monitor.status()["pending"] == 10


async def test_from_config_defaults_to_50_replies() -> None:
    client = FakeClient(
        [feed_item(notification_id=i, oid=i, parent=i) for i in range(1, 61)]
    )
    cfg = SimpleNamespace(bilibili=SimpleNamespace())
    monitor = BilibiliCommentMonitor.from_config(
        client, FakeEngine(), cfg, enabled=True
    )

    assert await monitor.poll_once() == 50
    assert monitor.status()["pending"] == 10


def test_parse_at_feed_item_maps_at_time_and_source_content() -> None:
    event = parse_feed_item(at_feed_item(), "at_feed")
    assert isinstance(event, CommentEvent)
    assert event.source == "at_feed"
    assert event.notification_id == 9
    assert event.ctime == 1710000000
    assert event.content == "这条评论 @了你"
    assert event.oid == 55
    assert event.parent_id == 66
    assert event.root_id == 66


def test_parse_feed_item_maps_fields() -> None:
    event = parse_feed_item(feed_item(notification_id=3, oid=7, parent=8, root=9))
    assert isinstance(event, CommentEvent)
    assert event.notification_id == 3
    assert event.oid == 7
    assert event.root_id == 9
    assert event.parent_id == 8
    assert event.target_type == "视频"


def test_business_id_maps_to_comment_type() -> None:
    # 与 BilibiliClient.COMMENT_TYPES 对齐：11=番剧、12=专栏/opus、17=动态，不能互串。
    assert parse_feed_item(feed_item(business_id=1)).target_type == "视频"
    assert parse_feed_item(feed_item(business_id=11)).target_type == "番剧"
    assert parse_feed_item(feed_item(business_id=12)).target_type == "专栏"
    assert parse_feed_item(feed_item(business_id=17)).target_type == "动态"
    for business_id in (1, 11, 12, 17):
        event = parse_feed_item(feed_item(business_id=business_id))
        assert event.comment_type == business_id


def test_unknown_business_id_falls_back_to_video_type() -> None:
    event = parse_feed_item(feed_item(business_id=99))

    assert event.comment_type == 1


async def test_reply_uses_business_comment_type() -> None:
    client = FakeClient([feed_item(business_id=17)])
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert client.sent[0]["type_"] == 17


async def test_generation_error_is_retried_next_poll() -> None:
    class FlakyEngine(FakeEngine):
        def __init__(self) -> None:
            super().__init__("好哦")
            self.calls = 0

        async def generate_comment_reply(self, ctx):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("provider timeout")
            self.contexts.append(ctx)
            return self.text

    client = FakeClient([feed_item(notification_id=1)])
    engine = FlakyEngine()
    monitor = _monitor(client, engine)

    # provider 超时按契约抛出：不记 processed，回池等下一轮，并进入退避。
    assert await monitor.poll_once() == 0
    assert client.sent == []
    assert monitor.status()["pending"] == 1
    assert monitor.next_poll_interval == 3600

    assert await monitor.poll_once() == 1
    assert len(client.sent) == 1
    assert monitor.status()["pending"] == 0
    assert monitor.next_poll_interval == 1800


async def test_failures_clear_on_normal_poll_without_events() -> None:
    client = FakeClient([], fail_feed=True)
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert monitor.status()["failures"] == 1

    client.fail_feed = False
    assert await monitor.poll_once() == 0
    assert monitor.status()["failures"] == 0
    assert monitor.next_poll_interval == 1800


async def test_replied_comment_is_persisted_across_restart(tmp_path) -> None:
    client = FakeClient([feed_item(notification_id=1)])
    monitor = BilibiliCommentMonitor(
        client,
        FakeEngine("好哦"),
        enabled=True,
        data_dir=tmp_path,
    )
    assert await monitor.poll_once() == 1
    state_file = tmp_path / "bilibili" / "comment_replies.json"
    assert state_file.exists()

    # 模拟进程重启：同一 feed 再拉一次，不能重复回复。
    client2 = FakeClient([feed_item(notification_id=1)])
    restarted = BilibiliCommentMonitor(
        client2,
        FakeEngine("好哦"),
        enabled=True,
        data_dir=tmp_path,
    )
    assert await restarted.poll_once() == 0
    assert client2.sent == []
