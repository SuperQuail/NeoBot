"""B站直播交互器：持久化、弹幕协议、过滤与自动回复。"""

from __future__ import annotations

import asyncio
import json
import struct
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from neobot_app.bilibili import live_interact
from neobot_app.bilibili.live_interact import (
    BilibiliLiveInteractor,
    decode_packets,
    encode_packet,
    parse_danmu_message,
)
from neobot_app.bilibili.live_protocol import LiveAuthError

_ROOM_INFO = {
    "room_info": {"room_id": 21452505, "title": "测试直播间", "live_status": 1},
    "anchor_info": {"base_info": {"uname": "主播"}},
}
_OFFLINE_ROOM_INFO = {
    "room_info": {"room_id": 21452505, "title": "测试直播间", "live_status": 0},
    "anchor_info": {"base_info": {"uname": "主播"}},
}
_NOW = datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc)


class _FakeClient:
    def __init__(
        self,
        *,
        room_info: dict | None = None,
        danmu_info: dict | None = None,
        my_uid: int = 7,
        send_ok: bool = True,
        buvid3: str = "buv-3",
    ) -> None:
        self.room_info = _ROOM_INFO if room_info is None else room_info
        self.danmu_info = danmu_info or {}
        self.my_uid = my_uid
        self.send_ok = send_ok
        self.buvid3 = buvid3
        self.user_agent = live_interact.DEFAULT_USER_AGENT
        self.room_calls: list[int] = []
        self.sent: list[tuple[int, str]] = []
        self.sent_targets: list[tuple[int, str]] = []

    def get_live_room_info(self, room_id: int) -> dict:
        self.room_calls.append(room_id)
        return self.room_info

    def get_live_danmu_info(self, room_id: int) -> dict:
        return self.danmu_info

    def send_danmaku(
        self, room_id: int, text: str, *, reply_mid: int = 0, reply_uname: str = ""
    ) -> bool:
        if not self.send_ok:
            return False
        self.sent.append((room_id, text))
        self.sent_targets.append((reply_mid, reply_uname))
        return True


class _FakeProvider:
    def __init__(self, content: str = "在呢", *, raises: bool = False, reply_to: int = 0) -> None:
        self.content = content
        self.raises = raises
        self.reply_to = reply_to
        self.messages: list[list[dict]] = []

    async def chat(self, messages: list[dict], tools=None) -> dict:
        self.messages.append(messages)
        if self.raises:
            raise RuntimeError("模型炸了")
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "send_reply",
                        "arguments": json.dumps(
                            {"text": self.content, "reply_to": self.reply_to}
                            if self.reply_to else {"text": self.content},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }


async def _enabled(
    tmp_path: Path,
    *,
    provider: object = None,
    bot_name: str = "小助手",
    cooldown: float = 0.0,
    at_only: bool = True,
    auto_reply: bool = True,
) -> tuple[BilibiliLiveInteractor, _FakeClient, _FakeProvider | None]:
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(
        client,
        provider=provider,
        bot_name=bot_name,
        data_dir=tmp_path,
        cooldown_seconds=cooldown,
        max_reply_chars=40,
        at_only=at_only,
    )
    await interactor.enable(5440, auto_reply=auto_reply)
    return interactor, client, provider  # type: ignore[return-value]


async def test_enable_persists_state_and_restores_on_start(tmp_path: Path) -> None:
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path)
    result = await interactor.enable(5440)
    assert result == {
        "ok": True,
        "room_id": 5440,
        "real_room_id": 21452505,
        "name": "主播",
        "auto_reply": True,
        "asr": False,
    }
    assert client.room_calls == [5440]
    state_path = tmp_path / "bilibili" / "live_interact.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state == {
        "rooms": {
            "5440": {
                "real_room_id": 21452505,
                "name": "主播",
                "auto_reply": True,
                "asr": False,
            }
        }
    }

    restarted = BilibiliLiveInteractor(None, data_dir=tmp_path)
    assert restarted.list_rooms() == [
        {
            "room_id": 5440,
            "real_room_id": 21452505,
            "name": "主播",
            "auto_reply": True,
            "asr": False,
        }
    ]
    await restarted.start()
    assert restarted.is_running is True
    assert len(restarted._tasks) == 1
    await restarted.stop()
    assert restarted.is_running is False


async def test_disable_and_auto_reply_persist(tmp_path: Path) -> None:
    interactor, _client, _provider = await _enabled(tmp_path)
    assert (await interactor.set_auto_reply(5440, False))["ok"] is True
    assert interactor.list_rooms()[0]["auto_reply"] is False
    state = json.loads((tmp_path / "bilibili" / "live_interact.json").read_text())
    assert state["rooms"]["5440"]["auto_reply"] is False

    assert (await interactor.set_auto_reply(9999, True))["ok"] is False
    assert (await interactor.disable(5440)) == {"ok": True, "room_id": 5440}
    assert interactor.list_rooms() == []
    assert (await interactor.disable(5440))["ok"] is False
    state = json.loads((tmp_path / "bilibili" / "live_interact.json").read_text())
    assert state == {"rooms": {}}


def test_encode_and_decode_packets_including_zlib() -> None:
    heartbeat = encode_packet(2)
    total, header_len, protover, op, seq = struct.unpack(">IHHII", heartbeat)
    assert (total, header_len, protover, op, seq) == (16, 16, 1, 2, 1)

    plain = encode_packet(5, b'{"cmd":"DANMU_MSG"}')
    assert decode_packets(plain) == [(5, b'{"cmd":"DANMU_MSG"}')]

    inner = encode_packet(5, b"one") + encode_packet(5, b"two")
    compressed = encode_packet(5, zlib.compress(inner), protover=2)
    assert decode_packets(compressed) == [(5, b"one"), (5, b"two")]
    assert decode_packets(plain[:8]) == []


def test_parse_danmu_message() -> None:
    payload = {
        "cmd": "DANMU_MSG:4:0:2:2:2:0",
        "info": [[], "你好", [12345, "观众甲"]],
    }
    assert parse_danmu_message(payload) == {
        "uid": 12345,
        "name": "观众甲",
        "text": "你好",
    }
    assert parse_danmu_message({"cmd": "SEND_GIFT", "info": []}) is None
    assert parse_danmu_message({"cmd": "DANMU_MSG", "info": []}) is None
    assert parse_danmu_message("not-json") is None


async def test_at_filter_generates_and_sends(tmp_path: Path) -> None:
    provider = _FakeProvider("在呢")
    interactor, client, _ = await _enabled(tmp_path, provider=provider)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 唱首歌"})
    assert client.sent == [(5440, "在呢")]
    messages = provider.messages[0]
    system = next(item for item in messages if item.get("role") == "system")
    user = next(item for item in messages if item.get("role") == "user")
    assert system["role"] == "system"
    assert "<直播场景>这是B站直播间。</直播场景>" in system["content"]
    assert "最多20个字" not in system["content"]
    assert "<活人感增强>" in system["content"]
    assert user["role"] == "user"
    assert "@小助手 唱首歌" in user["content"]
    assert "最近弹幕" in user["content"]

    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "随便说"})
    assert client.sent == [(5440, "在呢"), (5440, "在呢")]


async def test_at_only_false_replies_to_any_danmu(tmp_path: Path) -> None:
    provider = _FakeProvider()
    interactor, client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "随便说"})
    assert client.sent == [(5440, "在呢")]


async def test_self_message_and_disabled_room_are_ignored(tmp_path: Path) -> None:
    provider = _FakeProvider()
    interactor, client, _ = await _enabled(tmp_path, provider=provider)
    await interactor._handle_danmu("5440", {"uid": 7, "name": "自己", "text": "@小助手 我发的"})
    assert client.sent == []
    assert provider.messages == []

    off, off_client, off_provider = await _enabled(tmp_path, provider=_FakeProvider(), auto_reply=False)
    await off._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})
    assert off_client.sent == []
    assert off_provider.messages == []


async def test_provider_none_only_listens(tmp_path: Path) -> None:
    interactor, client, _ = await _enabled(tmp_path)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})
    assert client.sent == []


async def test_cooldown_blocks_until_elapsed(tmp_path: Path) -> None:
    provider = _FakeProvider()
    interactor, client, _ = await _enabled(tmp_path, provider=provider, cooldown=20.0)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 1"})
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 2"})
    assert len(client.sent) == 1
    assert len(provider.messages) >= 1

    interactor._last_reply_at["5440"] = time.monotonic() - 21.0
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 3"})
    assert len(client.sent) == 2


async def test_all_danmaku_trigger_without_minute_cap(tmp_path: Path) -> None:
    provider = _FakeProvider()
    interactor, client, _ = await _enabled(tmp_path, provider=provider, cooldown=0.0)
    for index in range(4):
        await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": f"@小助手 {index}"})
    assert len(client.sent) == 4


class _FakeWS:
    def __init__(self, messages: list[object]) -> None:
        self.messages = list(messages)
        self.sent: list[bytes] = []

    async def __aenter__(self) -> "_FakeWS":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    def __aiter__(self) -> "_FakeWS":
        return self

    async def __anext__(self) -> object:
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)


class _FakeSession:
    def __init__(self, ws: _FakeWS) -> None:
        self.ws = ws
        self.url = ""
        self.headers: dict = {}

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def ws_connect(self, url: str, *, headers: dict) -> _FakeWS:
        self.url = url
        self.headers = headers
        return self.ws


async def test_websocket_auth_packet_and_danmu_flow(tmp_path: Path, monkeypatch) -> None:
    provider = _FakeProvider("来了")
    client = _FakeClient(
        danmu_info={
            "token": "live-token",
            "host_list": [{"host": "broadcastlv.chat.bilibili.com", "wss_port": 443}],
        }
    )
    interactor = BilibiliLiveInteractor(client, provider=provider, bot_name="小助手", data_dir=tmp_path)
    await interactor.enable(5440)
    danmu = {
        "cmd": "DANMU_MSG:4:0:2:2:2:0",
        "info": [[], "@小助手 在吗", [8, "观众"]],
    }
    packet = encode_packet(5, json.dumps(danmu).encode("utf-8"))
    message = type("Msg", (), {"type": live_interact.aiohttp.WSMsgType.BINARY, "data": packet})()
    ws = _FakeWS([message])
    session = _FakeSession(ws)
    monkeypatch.setattr(live_interact.aiohttp, "ClientSession", lambda *a, **k: session)

    await interactor._connect_once("5440")
    await asyncio.gather(*interactor._reply_tasks)

    assert session.url == "wss://broadcastlv.chat.bilibili.com:443/sub"
    assert session.headers["Origin"] == "https://live.bilibili.com"
    op, body = decode_packets(ws.sent[0])[0]
    assert op == 7
    assert json.loads(body) == {
        "uid": 7,
        "roomid": 21452505,
        "protover": 3,
        "platform": "web",
        "type": 2,
        "buvid": "buv-3",
        "key": "live-token",
    }
    assert client.sent == [(5440, "来了")]


async def test_auth_reply_code_and_immediate_heartbeat(tmp_path: Path, monkeypatch) -> None:
    client = _FakeClient(
        danmu_info={
            "token": "live-token",
            "host_list": [{"host": "broadcastlv.chat.bilibili.com", "wss_port": 443}],
        }
    )
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path)
    await interactor.enable(5440)
    reply = encode_packet(8, json.dumps({"code": 0}).encode("utf-8"))
    ws = _FakeWS([type("Msg", (), {"type": live_interact.aiohttp.WSMsgType.BINARY, "data": reply})()])
    session = _FakeSession(ws)
    monkeypatch.setattr(live_interact.aiohttp, "ClientSession", lambda *a, **k: session)

    await interactor._connect_once("5440")

    assert session.headers["User-Agent"] == client.user_agent
    assert [op for op, _body in decode_packets(ws.sent[0])] == [7]
    assert [op for op, _body in decode_packets(ws.sent[1])] == [2]
    assert len(ws.sent) == 2

    bad = encode_packet(8, json.dumps({"code": -101}).encode("utf-8"))
    bad_ws = _FakeWS([type("Msg", (), {"type": live_interact.aiohttp.WSMsgType.BINARY, "data": bad})()])
    monkeypatch.setattr(live_interact.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(bad_ws))
    with pytest.raises(LiveAuthError):
        await interactor._connect_once("5440")


async def test_host_list_rotates_by_attempt(tmp_path: Path, monkeypatch) -> None:
    client = _FakeClient(
        danmu_info={
            "token": "live-token",
            "host_list": [
                {"host": "host-a", "wss_port": 443},
                {"host": "host-b", "wss_port": 8443},
            ],
        }
    )
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path)
    await interactor.enable(5440)
    sessions: list[_FakeSession] = []

    def _factory(*args: object, **kwargs: object) -> _FakeSession:
        session = _FakeSession(_FakeWS([]))
        sessions.append(session)
        return session

    monkeypatch.setattr(live_interact.aiohttp, "ClientSession", _factory)
    await interactor._connect_once("5440", 0)
    await interactor._connect_once("5440", 1)

    assert [session.url for session in sessions] == [
        "wss://host-a:443/sub",
        "wss://host-b:8443/sub",
    ]


def _gift_body(index: int) -> bytes:
    payload = {
        "cmd": "SEND_GIFT",
        "data": {
            "uid": 8,
            "uname": "观众",
            "giftName": f"礼物{index}",
            "num": 1,
            "total_coin": 100,
            "rnd": f"r{index}",
            "tid": f"t{index}",
            "timestamp": 1700000000,
        },
    }
    return json.dumps(payload).encode("utf-8")


async def test_recent_events_dedupes_gift_and_emits_callback(tmp_path: Path) -> None:
    seen = []
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path, on_event=seen.append)
    await interactor.enable(5440, auto_reply=False)

    body = _gift_body(1)
    await interactor._handle_packet("5440", 5, body)
    await interactor._handle_packet("5440", 5, body)  # 重复投递按 rnd/tid 去重
    super_chat = {
        "cmd": "SUPER_CHAT_MESSAGE",
        "data": {
            "uid": 9,
            "price": 30,
            "message": "加油",
            "id": 100,
            "start_time": 1700000001,
            "user_info": {"uname": "老板"},
        },
    }
    await interactor._handle_packet("5440", 5, json.dumps(super_chat).encode("utf-8"))
    mirror = {"cmd": "DANMU_MSG_MIRROR", "info": [[], "镜像", [10, "别人"]]}
    await interactor._handle_packet("5440", 5, json.dumps(mirror).encode("utf-8"))

    events = interactor.recent_events(5440)
    assert [event.kind for event in events] == ["gift", "super_chat"]
    assert events[0].text == "礼物1"
    assert events[0].value == 100
    assert events[1].name == "老板"
    assert events[1].value == 30
    assert seen == events
    assert interactor.get_history(5440) == []


async def test_recent_events_keeps_latest_100(tmp_path: Path) -> None:
    interactor = BilibiliLiveInteractor(_FakeClient(), data_dir=tmp_path)
    await interactor.enable(5440, auto_reply=False)
    for index in range(105):
        await interactor._handle_packet("5440", 5, _gift_body(index))

    events = interactor.recent_events(5440, 100)
    assert len(events) == 100
    assert events[0].text == "礼物5"
    assert events[-1].text == "礼物104"
    assert interactor.recent_events(5440, 2)[-1].text == "礼物104"
    assert interactor.recent_events(9999) == []


async def test_reply_is_cleaned_and_truncated(tmp_path: Path) -> None:
    provider = _FakeProvider("好哦")
    interactor, client, _ = await _enabled(tmp_path, provider=provider)
    interactor._max_reply_chars = 5
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})
    assert len(client.sent) == 1
    assert len(client.sent[0][1]) <= 5


async def test_provider_error_and_send_failure_do_not_raise(tmp_path: Path) -> None:
    broken = _FakeProvider(raises=True)
    interactor, client, _ = await _enabled(tmp_path, provider=broken)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})
    assert client.sent == []

    failing = _FakeClient(send_ok=False)
    provider = _FakeProvider()
    failing_interactor = BilibiliLiveInteractor(failing, provider=provider, bot_name="小助手", data_dir=tmp_path)
    await failing_interactor.enable(5440)
    await failing_interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})
    assert failing.sent == []


async def test_public_send_danmaku(tmp_path: Path) -> None:
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path)
    assert (await interactor.send_danmaku(5440, "  hi  "))["ok"] is True
    assert client.sent == [(5440, "hi")]
    assert (await interactor.send_danmaku(0, "hi"))["ok"] is False
    assert (await interactor.send_danmaku(5440, "  "))["ok"] is False
    assert (await BilibiliLiveInteractor(None, data_dir=tmp_path).send_danmaku(5440, "hi"))["ok"] is False


# ── 仅开播交互 ──


async def test_offline_room_skips_auto_reply_and_manual_send(tmp_path: Path) -> None:
    client = _FakeClient(room_info=_OFFLINE_ROOM_INFO)
    provider = _FakeProvider()
    interactor = BilibiliLiveInteractor(
        client,
        provider=provider,
        bot_name="小助手",
        data_dir=tmp_path,
        cooldown_seconds=0.0,
    )
    await interactor.enable(5440)

    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 hi"})

    assert client.sent == []
    assert provider.messages == []
    assert (await interactor.send_danmaku(5440, "hi")) == {
        "ok": False,
        "error": "未开播，不互动",
    }
    # 下播仍保留 WSS 收到的弹幕历史
    assert interactor.get_history(5440)[0]["text"] == "@小助手 hi"


async def test_live_status_is_cached_for_60_seconds(tmp_path: Path) -> None:
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(client, data_dir=tmp_path)
    await interactor.enable(5440)

    assert await interactor.is_live(5440) is True
    assert await interactor.is_live(5440) is True
    assert client.room_calls == [5440, 5440]

    interactor._live_cache["5440"] = (time.monotonic() - 61.0, False)
    client.room_info = _OFFLINE_ROOM_INFO
    assert await interactor.is_live(5440) is False
    assert client.room_calls == [5440, 5440, 5440]


# ── 房间历史 ──


async def test_history_keeps_latest_500_danmu(tmp_path: Path) -> None:
    interactor, _client, _provider = await _enabled(tmp_path, auto_reply=False)
    for index in range(505):
        await interactor._handle_danmu("5440", {"uid": index, "name": f"观众{index}", "text": f"弹幕{index}"})

    history = interactor.get_history(5440)
    assert len(history) == 500
    assert history[0]["text"] == "弹幕5"
    assert history[-1]["text"] == "弹幕504"
    assert set(history[0]) == {"uid", "name", "text", "time", "ts", "at_me"}
    assert len(history[0]["time"]) == 8
    assert interactor.get_history(5440, 2)[-1]["text"] == "弹幕504"
    assert interactor.get_history(9999) == []


# ── 定时弹幕 ──


async def test_daily_schedule_fires_once_and_persists(tmp_path: Path) -> None:
    provider = _FakeProvider("来啦")
    interactor, client, _ = await _enabled(tmp_path, provider=provider, auto_reply=False)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "今天播什么"})

    created = await interactor.schedule(5440, "9:30", "daily", "宣传新视频")
    assert created["ok"] is True
    assert created["schedule"]["time"] == "09:30"

    fired = await interactor._scan_schedules(_NOW)
    assert fired == [{"room_id": 5440, "schedule_id": created["schedule"]["id"], "text": "来啦"}]
    assert client.sent == [(5440, "来啦")]
    prompt = provider.messages[-1][1]["content"]
    assert "宣传新视频" in prompt
    assert "今天播什么" in prompt

    assert await interactor._scan_schedules(_NOW) == []
    assert len(client.sent) == 1

    state = json.loads((tmp_path / "bilibili" / "live_interact.json").read_text(encoding="utf-8"))
    saved = state["rooms"]["5440"]["schedules"][0]
    assert saved["last_fired_date"] == "2026-05-01"
    assert saved["recurrence"] == "daily"

    restarted = BilibiliLiveInteractor(None, data_dir=tmp_path)
    assert restarted.list_schedules(5440)[0]["prompt"] == "宣传新视频"

    assert len(await interactor._scan_schedules(_NOW + timedelta(days=1))) == 1
    assert len(client.sent) == 2


async def test_schedule_skips_offline_and_does_not_backfill(tmp_path: Path) -> None:
    client = _FakeClient(room_info=_OFFLINE_ROOM_INFO)
    provider = _FakeProvider()
    interactor = BilibiliLiveInteractor(client, provider=provider, bot_name="小助手", data_dir=tmp_path)
    await interactor.enable(5440)
    await interactor.schedule(5440, "09:30", "daily", "宣传")

    assert await interactor._scan_schedules(_NOW) == []
    assert client.sent == []
    assert provider.messages == []
    assert interactor.list_schedules(5440)[0]["last_fired_date"] == "2026-05-01"

    # 同一时段内即使随后开播也不补发
    client.room_info = _ROOM_INFO
    interactor._live_cache.clear()
    assert await interactor._scan_schedules(_NOW) == []
    assert client.sent == []


async def test_weekly_schedule_waits_seven_days(tmp_path: Path) -> None:
    interactor, client, _ = await _enabled(tmp_path, provider=_FakeProvider("周更"), auto_reply=False)
    await interactor.schedule(5440, "09:30", "weekly", "周更提醒")

    assert len(await interactor._scan_schedules(_NOW)) == 1
    assert await interactor._scan_schedules(_NOW + timedelta(days=3)) == []
    assert len(await interactor._scan_schedules(_NOW + timedelta(days=7))) == 1
    assert len(client.sent) == 2


async def test_once_schedule_fires_only_once(tmp_path: Path) -> None:
    interactor, client, _ = await _enabled(tmp_path, provider=_FakeProvider("一次"), auto_reply=False)
    await interactor.schedule(5440, "09:30", "once", "只发一次")

    assert len(await interactor._scan_schedules(_NOW)) == 1
    assert await interactor._scan_schedules(_NOW + timedelta(days=1)) == []
    assert len(client.sent) == 1


async def test_schedule_validation_and_delete(tmp_path: Path) -> None:
    interactor, _client, _provider = await _enabled(tmp_path)

    assert (await interactor.schedule(9999, "09:30", "daily", "x"))["error"] == "房间未启用"
    assert (await interactor.schedule(5440, "25:00", "daily", "x"))["error"] == "时间格式应为 HH:MM"
    assert (await interactor.schedule(5440, "09:30", "hourly", "x"))["error"] == "recurrence 只能是 once/daily/weekly"
    assert (await interactor.schedule(5440, "09:30", "daily", " "))["error"] == "prompt 不能为空"

    created = await interactor.schedule(5440, "09:30", "daily", "x")
    schedule_id = created["schedule"]["id"]
    await interactor.enable(5440)  # 重新启用不丢定时弹幕
    assert interactor.list_schedules(5440)[0]["id"] == schedule_id
    assert (await interactor.delete_schedule(5440, "missing"))["ok"] is False
    assert (await interactor.delete_schedule(5440, schedule_id)) == {
        "ok": True,
        "room_id": 5440,
        "schedule_id": schedule_id,
    }
    assert interactor.list_schedules() == []


class _FakeMedia:
    def __init__(self) -> None:
        self.captures: list[int] = []

    async def capture_frame(self, room_id: int) -> dict:
        self.captures.append(room_id)
        return {"ok": True, "path": "frame.jpg", "bytes": b"", "room_id": room_id}


class _FakeVision:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict]) -> dict:
        self.calls += 1
        return {"content": "主播正在挥手"}


async def test_reply_does_not_auto_capture_frame_by_default(tmp_path: Path) -> None:
    provider = _FakeProvider("欢迎")
    interactor, client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    media = _FakeMedia()
    vision = _FakeVision()
    interactor._media = media
    interactor._vision_provider = vision
    interactor._describe_frame = lambda snapshot: _async_value("主播正在挥手")  # type: ignore[method-assign]

    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "在吗"})
    assert media.captures == []
    assert client.sent == [(5440, "欢迎")]
    last_user = next(
        item for item in reversed(provider.messages[-1]) if item.get("role") == "user"
    )
    assert "主播正在挥手" not in last_user["content"]


async def _async_value(value):
    return value


class _FakeWilling:
    def __init__(self, should_reply: bool) -> None:
        self.should_reply_value = should_reply
        self.calls: list[dict] = []
        self.coefficients: dict[str, float] = {}

    def evaluate_live(self, **kwargs):
        self.calls.append(kwargs)
        coefficient = self.coefficients.get(kwargs.get("room_id") and f"live:{kwargs['room_id']}")
        should = self.should_reply_value
        if coefficient is not None:
            should = coefficient > 0
        return SimpleNamespace(
            should_reply=should,
            probability=1.0 if should else 0.0,
            reasons=("test",),
        )

    def set_runtime_conversation_coefficient(self, conv_id, value):
        self.coefficients[conv_id] = value
        return "ok"

    def get_runtime_conversation_coefficient(self, conv_id):
        return self.coefficients.get(conv_id)

    def remove_runtime_conversation_coefficient(self, conv_id):
        self.coefficients.pop(conv_id, None)
        return "ok"

    def get_runtime_config_summary(self):
        return "test"


async def test_live_auto_reply_uses_willingness_without_at(tmp_path: Path) -> None:
    provider = _FakeProvider("欢迎")
    interactor, client, _ = await _enabled(
        tmp_path, provider=provider, at_only=True
    )
    willing = _FakeWilling(True)
    interactor._willing_service = willing

    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "在吗"})
    assert client.sent == [(5440, "欢迎")]
    assert willing.calls and willing.calls[0]["room_id"] == 5440


async def test_live_auto_reply_skips_when_willingness_denies(tmp_path: Path) -> None:
    provider = _FakeProvider("欢迎")
    interactor, client, _ = await _enabled(
        tmp_path, provider=provider, at_only=False
    )
    interactor._willing_service = _FakeWilling(False)

    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "在吗"})
    assert client.sent == []



def test_mention_aliases_are_used_for_at_detection(tmp_path: Path) -> None:
    interactor = BilibiliLiveInteractor(
        None,
        bot_name="QQ名",
        data_dir=tmp_path,
        mention_names=["B站小号"],
    )
    assert interactor._mentions_bot("@B站小号 在吗") is True
    assert interactor._mentions_bot("@别人 在吗") is False



class _FakeFlowRegistry:
    def __init__(self) -> None:
        self.prompts: list[tuple] = []
        self.requests: list[tuple] = []

    def record_prompt(self, key, **kwargs):
        self.prompts.append((key, kwargs))

    def record_request(self, key, **kwargs):
        self.requests.append((key, kwargs))


async def test_live_reply_records_flow_registry(tmp_path: Path) -> None:
    provider = _FakeProvider("欢迎")
    interactor, _client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    registry = _FakeFlowRegistry()
    interactor._flow_registry = registry

    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "在吗"})

    assert registry.prompts and registry.prompts[0][0] == "bilibili_live:5440"
    assert registry.requests and registry.requests[0][1]["messages"]



async def test_live_splitter_sends_short_segments(tmp_path: Path) -> None:
    provider = _FakeProvider("今天天气不错。我们来聊聊游戏吧。")
    interactor, client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "随便说"})
    assert client.sent
    assert all(len(text) <= 20 for _, text in client.sent)


async def test_overlong_live_reply_is_rejected_for_rewrite(tmp_path: Path) -> None:
    provider = _FakeProvider("这是一条非常非常非常长的直播弹幕回复超过二十个字了")
    interactor, client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "随便说"})
    assert client.sent == []
    assert len(provider.messages) >= 2



async def test_asr_switch_controls_live_prompt_context(tmp_path: Path) -> None:
    provider = _FakeProvider("好哦")
    interactor, _client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    interactor._asr_service = object()
    interactor.transcribe = AsyncMock(  # type: ignore[method-assign]
        return_value={"ok": True, "text": "主播刚说晚上好"}
    )

    async def _user_content() -> str:
        messages = provider.messages[0]
        return next(
            str(item.get("content") or "")
            for item in messages
            if item.get("role") == "user"
        )

    await interactor.set_asr(5440, True)
    await interactor._generate_reply("在吗", 5440)
    on_content = await _user_content()
    assert "<直播语音>主播刚说晚上好</直播语音>" in on_content
    calls_after_on = interactor.transcribe.await_count  # type: ignore[attr-defined]

    await interactor.set_asr(5440, False)
    provider.messages.clear()
    await interactor._generate_reply("在吗", 5440)
    off_content = await _user_content()
    assert "<直播语音>" not in off_content
    assert interactor.transcribe.await_count == calls_after_on  # type: ignore[attr-defined]



async def test_live_reply_passes_reply_to(tmp_path: Path) -> None:
    provider = _FakeProvider("回你", reply_to=8)
    interactor, client, _ = await _enabled(tmp_path, provider=provider)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众", "text": "@小助手 在吗"})
    assert client.sent == [(5440, "回你")]
    assert client.sent_targets == [(8, "观众")]


async def test_live_persona_uses_live_chat_section(tmp_path: Path) -> None:
    from neobot_app.bilibili.prompts import LiveDanmakuContext, build_live_danmaku_prompt

    class _Store:
        def get(self, section, sub="template", default=""):
            return "自定义直播人格" if section == "live_chat" else ""

    interactor = BilibiliLiveInteractor(None, data_dir=tmp_path, prompt_store=_Store())
    assert interactor._live_persona() == "自定义直播人格"
    system, _user = build_live_danmaku_prompt(LiveDanmakuContext(), interactor._live_persona())
    assert system == "自定义直播人格"


async def test_history_keeps_500_for_prompt(tmp_path: Path) -> None:
    interactor = BilibiliLiveInteractor(None, data_dir=tmp_path)
    for index in range(520):
        interactor._record_history("5440", {"uid": 8, "name": "观众", "text": f"m{index}"})
    lines = interactor.format_history(5440).splitlines()
    assert len(lines) == 500
    assert "m0" not in lines[0]
    assert "m519" in lines[-1]



async def test_screenshot_replies_captures_frame_when_enabled(tmp_path: Path) -> None:
    provider = _FakeProvider("欢迎")
    interactor, client, _ = await _enabled(tmp_path, provider=provider, at_only=False)
    media = _FakeMedia()
    interactor._media = media
    interactor._screenshot_replies = True

    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众", "text": "在吗"})
    assert media.captures == [5440]
    assert client.sent == [(5440, "欢迎")]



async def test_live_summarizes_every_200(tmp_path: Path) -> None:
    provider = _FakeProvider("这直播间在聊游戏")
    archive = SimpleNamespace(set=AsyncMock())
    interactor = BilibiliLiveInteractor(
        _FakeClient(),
        provider=provider,
        bot_name="小助手",
        data_dir=tmp_path,
        archive_service=archive,
        summary_every=200,
    )
    interactor._chat = AsyncMock(return_value="这直播间在聊游戏")  # type: ignore[method-assign]
    for index in range(200):
        interactor._record_history("5440", {"uid": 8, "name": "观众", "text": f"弹幕{index}"})
    await asyncio.gather(*interactor._summary_tasks)
    assert interactor._room_memory["5440"] == "这直播间在聊游戏"
    archive.set.assert_awaited_once()



def test_live_willingness_coefficient(tmp_path: Path) -> None:
    willing = _FakeWilling(True)
    interactor = BilibiliLiveInteractor(None, data_dir=tmp_path, willing_service=willing)
    assert interactor._should_reply("5440", {"uid": 8}, "在吗") is True
    interactor.set_live_willingness(5440, 0.0)
    assert interactor._should_reply("5440", {"uid": 8}, "在吗") is False
    assert interactor.get_live_willingness(5440)["coefficient"] == 0.0
    interactor.remove_live_willingness(5440)
    assert interactor._should_reply("5440", {"uid": 8}, "在吗") is True


async def test_ensure_started_starts_listener_when_not_running(tmp_path: Path) -> None:
    """监听器没在跑时要能原地拉起，否则登录后开监听是假成功。"""
    interactor = BilibiliLiveInteractor(None, data_dir=tmp_path)
    assert interactor.is_running is False

    await interactor.ensure_started()
    assert interactor.is_running is True

    await interactor.ensure_started()
    assert interactor.is_running is True

    # 登录后直接开房间：ensure_started 之后 enable 会真正建监听任务。
    assert (await interactor.enable(5440))["ok"] is True
    assert "5440" in interactor._tasks

    await interactor.stop()
    assert interactor.is_running is False
