"""BilibiliPrivateMonitor 测试：默认关闭、跳过自己、旧消息不丢、去重、合并多条、发送。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.bilibili.private_monitor import BilibiliPrivateMonitor


class FakeEngine:
    def __init__(self, text: str | None = "在的") -> None:
        self.text = text
        self.available = True
        self.contexts = []

    async def generate_private_reply(self, ctx):
        self.contexts.append(ctx)
        return self.text


class FakeClient:
    my_uid = 999

    def __init__(self, sessions=None, messages=None, *, fail_send: bool = False) -> None:
        self.sessions = list(sessions or [])
        self.messages = dict(messages or {})
        self.fail_send = fail_send
        self.sent: list[tuple[int, str]] = []

    def get_sessions(self, count: int = 30):
        return self.sessions

    def get_messages(self, talker_id: int, size: int = 5):
        return list(self.messages.get(talker_id, []))[-size:]

    def send_message(self, receiver_id: int, text: str) -> bool:
        if self.fail_send:
            return False
        self.sent.append((receiver_id, text))
        return True


def message(
    sender_uid: int = 55,
    text: str = "在吗",
    *,
    timestamp: int = 0,
    msg_key: str = "",
    msg_type: int = 1,
) -> SimpleNamespace:
    content = json.dumps({"content": text}, ensure_ascii=False) if msg_type == 1 else "{}"
    return SimpleNamespace(
        talker_id=sender_uid,
        sender_uid=sender_uid,
        msg_type=msg_type,
        content=content,
        timestamp=timestamp,
        msg_key=msg_key or f"55_{timestamp}_{text[:20]}",
        is_self=sender_uid == FakeClient.my_uid,
    )


def session(talker_id: int = 55) -> SimpleNamespace:
    return SimpleNamespace(talker_id=talker_id, last_msg=None)


def _monitor(client, engine=None, **kwargs) -> BilibiliPrivateMonitor:
    values = {
        "enabled": True,
        "poll_interval_seconds": 1800,
        "max_replies_per_poll": 3,
        "reply_cooldown_seconds": 0,
    }
    values.update(kwargs)
    return BilibiliPrivateMonitor(client, engine or FakeEngine(), **values)


async def test_disabled_monitor_does_not_poll() -> None:
    client = FakeClient([session()], {55: [message()]})
    engine = FakeEngine()
    monitor = BilibiliPrivateMonitor(client, engine, enabled=False)

    assert await monitor.poll_once() == 0
    assert engine.contexts == []
    await monitor.start()
    assert monitor.is_running is False


async def test_new_message_generates_and_sends() -> None:
    client = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    engine = FakeEngine("在的")
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 1
    assert client.sent == [(55, "在的")]
    ctx = engine.contexts[0]
    assert ctx.current_message == "在吗"
    assert ctx.sender_uid == 55
    assert any(item["content"] == "在吗" for item in ctx.history)


async def test_self_message_is_skipped() -> None:
    client = FakeClient(
        [session()],
        {55: [message(FakeClient.my_uid, "我自己说的", timestamp=100)]},
    )
    engine = FakeEngine()
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 0
    assert client.sent == []
    assert engine.contexts == []


async def test_old_message_is_not_dropped_by_start_time() -> None:
    # 之前没回复的旧私信也回，不再因早于监控启动时间被丢。
    client = FakeClient([session()], {55: [message(55, "旧消息", timestamp=1)]})
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert client.sent == [(55, "在的")]


async def test_duplicate_message_is_not_answered_twice() -> None:
    client = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    monitor = _monitor(client)

    assert await monitor.poll_once() == 1
    assert await monitor.poll_once() == 0
    assert len(client.sent) == 1


async def test_multiple_messages_from_one_session_merge_into_one_reply() -> None:
    client = FakeClient(
        [session()],
        {55: [message(55, "在吗", timestamp=100), message(55, "问你个事", timestamp=101)]},
    )
    engine = FakeEngine()
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 1
    assert len(client.sent) == 1
    assert engine.contexts[0].current_message == "问你个事"
    contents = [item["content"] for item in engine.contexts[0].history]
    assert "在吗" in contents and "问你个事" in contents


async def test_non_text_message_is_skipped() -> None:
    client = FakeClient([session()], {55: [message(55, "", msg_type=2, timestamp=100)]})
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert client.sent == []


async def test_skip_from_engine_marks_processed() -> None:
    client = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    engine = FakeEngine(None)
    monitor = _monitor(client, engine)

    assert await monitor.poll_once() == 0
    assert await monitor.poll_once() == 0
    assert len(engine.contexts) == 1


async def test_send_failure_increases_backoff_and_retries_next_poll() -> None:
    client = FakeClient(
        [session()], {55: [message(55, "在吗", timestamp=100)]}, fail_send=True
    )
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert monitor.status()["pending_sessions"] == 1
    assert monitor.next_poll_interval == 3600

    client.fail_send = False
    assert await monitor.poll_once() == 1
    assert monitor.status()["pending_sessions"] == 0
    assert monitor.status()["processed_messages"] == 1


async def test_max_replies_per_poll_continues_next_poll() -> None:
    client = FakeClient(
        [session(55), session(66), session(77)],
        {
            55: [message(55, "a", timestamp=100)],
            66: [message(66, "b", timestamp=100)],
            77: [message(77, "c", timestamp=100)],
        },
    )
    monitor = _monitor(client, max_replies_per_poll=2)

    assert await monitor.poll_once() == 2
    assert await monitor.poll_once() == 1
    assert len(client.sent) == 3


def test_default_poll_interval_is_1800() -> None:
    assert BilibiliPrivateMonitor().next_poll_interval == 1800
    assert BilibiliPrivateMonitor(poll_interval_seconds=0).next_poll_interval == 1800
    cfg = SimpleNamespace(bilibili=SimpleNamespace())
    assert BilibiliPrivateMonitor.from_config(None, None, cfg).next_poll_interval == 1800


def test_default_limits_are_50() -> None:
    cfg = SimpleNamespace(bilibili=SimpleNamespace())
    monitor = BilibiliPrivateMonitor.from_config(None, None, cfg)
    assert monitor._max_per_poll == 50
    assert monitor._session_check_count == 50


async def test_session_check_count_defaults_to_50() -> None:
    class CountingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.counts: list[int] = []

        def get_sessions(self, count: int = 30):
            self.counts.append(count)
            return []

    client = CountingClient()
    monitor = BilibiliPrivateMonitor(client, FakeEngine(), enabled=True)

    assert await monitor.poll_once() == 0
    assert client.counts == [50]


async def test_default_max_replies_per_poll_is_50() -> None:
    talkers = list(range(1000, 1060))
    client = FakeClient(
        [session(talker) for talker in talkers],
        {talker: [message(talker, f"m{talker}", timestamp=100)] for talker in talkers},
    )
    monitor = BilibiliPrivateMonitor(client, FakeEngine(), enabled=True)

    assert await monitor.poll_once() == 50
    assert len(client.sent) == 50
    assert await monitor.poll_once() == 10
    assert len(client.sent) == 60


async def test_from_config_defaults_to_50_replies() -> None:
    talkers = list(range(1000, 1060))
    client = FakeClient(
        [session(talker) for talker in talkers],
        {talker: [message(talker, f"m{talker}", timestamp=100)] for talker in talkers},
    )
    cfg = SimpleNamespace(bilibili=SimpleNamespace())
    monitor = BilibiliPrivateMonitor.from_config(
        client, FakeEngine(), cfg, enabled=True
    )

    assert await monitor.poll_once() == 50
    assert len(client.sent) == 50


async def test_start_stop_lifecycle() -> None:
    monitor = _monitor(FakeClient())

    await monitor.start()
    assert monitor.is_running is True
    await monitor.stop()
    assert monitor.is_running is False


async def test_replied_message_persists_across_restart(tmp_path) -> None:
    client = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    monitor = _monitor(client, data_dir=tmp_path)

    assert await monitor.poll_once() == 1
    state_file = tmp_path / "bilibili" / "private_replies.json"
    assert state_file.exists()

    # 模拟进程重启：同一份私信再拉一次，不能重复回。
    client2 = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    restarted = _monitor(client2, data_dir=tmp_path)
    assert await restarted.poll_once() == 0
    assert client2.sent == []


async def test_failures_clear_on_normal_poll_without_new_messages() -> None:
    client = FakeClient(
        [session()], {55: [message(55, "在吗", timestamp=100)]}, fail_send=True
    )
    monitor = _monitor(client)

    assert await monitor.poll_once() == 0
    assert monitor.status()["failures"] == 1
    assert monitor.next_poll_interval == 3600

    # 下一轮没有新私信（即使失败计数曾经顶格）也要清零退避。
    client.messages[55] = []
    client.fail_send = False
    assert await monitor.poll_once() == 0
    assert monitor.status()["failures"] == 0
    assert monitor.next_poll_interval == 1800


async def test_generation_error_is_retried_next_poll() -> None:
    class FlakyEngine(FakeEngine):
        def __init__(self) -> None:
            super().__init__("在的")
            self.calls = 0

        async def generate_private_reply(self, ctx):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("provider timeout")
            self.contexts.append(ctx)
            return self.text

    client = FakeClient([session()], {55: [message(55, "在吗", timestamp=100)]})
    engine = FlakyEngine()
    monitor = _monitor(client, engine)

    # provider 超时按契约抛出：不记 processed，会话回池等下一轮。
    assert await monitor.poll_once() == 0
    assert client.sent == []
    assert monitor.status()["pending_sessions"] == 1
    assert monitor.next_poll_interval == 3600

    assert await monitor.poll_once() == 1
    assert client.sent == [(55, "在的")]
    assert monitor.status()["pending_sessions"] == 0
    assert monitor.next_poll_interval == 1800
