"""bilibili_live skill：工具接口、JSON 输出与错误中文。"""

from __future__ import annotations

import json
from pathlib import Path

from neobot_app.bilibili.live_interact import BilibiliLiveInteractor
from neobot_app.skills.bilibili_live import BilibiliLiveSkill

_ROOM_INFO = {
    "room_info": {"room_id": 21452505, "title": "测试直播间", "live_status": 1},
    "anchor_info": {"base_info": {"uname": "主播"}},
}
_OFFLINE_ROOM_INFO = {
    "room_info": {"room_id": 21452505, "title": "测试直播间", "live_status": 0},
    "anchor_info": {"base_info": {"uname": "主播"}},
}


class _FakeClient:
    my_uid = 7

    def __init__(self) -> None:
        self.room_info = _ROOM_INFO
        self.sent: list[tuple[int, str]] = []

    def get_live_room_info(self, room_id: int) -> dict:
        return self.room_info

    def send_danmaku(self, room_id: int, text: str) -> bool:
        self.sent.append((room_id, text))
        return True


class _FakeProvider:
    async def chat(self, messages: list[dict]) -> dict:
        return {"content": "在呢"}


async def _skill(
    tmp_path: Path, *, auto_reply: bool = True
) -> tuple[BilibiliLiveSkill, BilibiliLiveInteractor, _FakeClient]:
    client = _FakeClient()
    interactor = BilibiliLiveInteractor(
        client,
        provider=_FakeProvider(),
        bot_name="小助手",
        data_dir=tmp_path,
        cooldown_seconds=0.0,
    )
    await interactor.enable(5440, auto_reply=auto_reply)
    return BilibiliLiveSkill(interactor), interactor, client


def test_skill_exposes_expected_tools() -> None:
    names = {tool["function"]["name"] for tool in BilibiliLiveSkill(None).get_tools()}
    assert names == {
        "status",
        "send_danmaku",
        "read_history",
        "enable",
        "disable",
        "schedule",
        "list_schedules",
        "delete_schedule",
        "recent_events",
        "record_clip",
        "snapshot",
        "transcribe",
        "get_live_willingness",
        "set_live_willingness",
        "remove_live_willingness",
    }


async def test_skill_enable_and_status(tmp_path: Path) -> None:
    skill, _interactor, _client = await _skill(tmp_path)
    assert (await BilibiliLiveSkill(None).execute("status", {})) == json.dumps(
        {"ok": False, "error": "B站直播交互器不可用"}, ensure_ascii=False
    )

    raw = await skill.execute("status", {"room_id": 5440})
    status = json.loads(raw)
    assert status["ok"] is True
    assert status["enabled"] is True
    assert status["live"] is True
    assert status["auto_reply"] is True
    assert status["name"] == "主播"
    assert "主播" in raw and "\\u" not in raw

    rooms = json.loads(await skill.execute("status", {}))
    assert rooms["ok"] is True
    assert [room["room_id"] for room in rooms["rooms"]] == [5440]

    disabled = json.loads(
        await skill.execute("disable", {"room_id": 5440, "confirm": True})
    )
    assert disabled["ok"] is True
    assert "写操作" in disabled["note"]


async def test_skill_send_danmaku_and_read_history(tmp_path: Path) -> None:
    skill, interactor, client = await _skill(tmp_path, auto_reply=False)
    await interactor._handle_danmu("5440", {"uid": 8, "name": "观众甲", "text": "第一句"})
    await interactor._handle_danmu("5440", {"uid": 9, "name": "观众乙", "text": "第二句"})

    history = json.loads(await skill.execute("read_history", {"room_id": 5440}))
    assert history["ok"] is True
    assert history["count"] == 2
    assert [item["text"] for item in history["history"]] == ["第一句", "第二句"]

    raw = await skill.execute(
        "send_danmaku", {"room_id": 5440, "text": " hi ", "confirm": True}
    )
    sent = json.loads(raw)
    assert sent["ok"] is True
    assert sent["text"] == "hi"
    assert "当前B站账号" in sent["note"]
    assert client.sent == [(5440, "hi")]

    client.room_info = _OFFLINE_ROOM_INFO
    interactor._live_cache.clear()
    offline = json.loads(
        await skill.execute(
            "send_danmaku", {"room_id": 5440, "text": "hi", "confirm": True}
        )
    )
    assert offline["ok"] is False
    assert offline["error"] == "未开播，不互动"


async def test_skill_schedule_list_delete(tmp_path: Path) -> None:
    skill, _interactor, _client = await _skill(tmp_path)

    created = json.loads(
        await skill.execute(
            "schedule",
            {
                "room_id": 5440,
                "time": "09:30",
                "recurrence": "daily",
                "prompt": "宣传新视频",
                "confirm": True,
            },
        )
    )
    assert created["ok"] is True
    assert created["schedule"]["time"] == "09:30"
    assert "写操作" in created["note"]
    schedule_id = created["schedule"]["id"]

    listed = json.loads(await skill.execute("list_schedules", {}))
    assert listed["ok"] is True
    assert [item["room_id"] for item in listed["schedules"]] == [5440]

    deleted = json.loads(
        await skill.execute(
            "delete_schedule",
            {"room_id": 5440, "schedule_id": schedule_id, "confirm": True},
        )
    )
    assert deleted["ok"] is True
    assert deleted["schedule_id"] == schedule_id
    assert json.loads(await skill.execute("list_schedules", {}))["schedules"] == []


class _StateLive:
    """只暴露开播三态与房间列表的交互器替身。"""

    def __init__(self, status: dict) -> None:
        self.status = status
        self.rooms = [{"room_id": 5440, "name": "主播", "auto_reply": True}]

    async def live_status(self, room_id: int) -> dict:
        return dict(self.status)

    def list_rooms(self) -> list[dict]:
        return list(self.rooms)

    def list_schedules(self, room_id: int | None = None) -> list[dict]:
        return []


class _DeadService:
    """已失效的登录态：refresh 之后仍然不可用。"""

    def __init__(self) -> None:
        self.available = False
        self.refresh_calls = 0

    async def refresh(self) -> bool:
        self.refresh_calls += 1
        return False

    def status(self) -> dict:
        return {"error": "B站登录态已过期，请重新扫码登录"}


class _EnableLive:
    """只记录 enable 参数的交互器替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []
        self.started = False

    async def ensure_started(self) -> None:
        self.started = True

    async def enable(self, room_id: int, *, auto_reply: bool = True) -> dict:
        self.calls.append((room_id, auto_reply))
        return {"ok": True, "room_id": room_id, "auto_reply": auto_reply}


async def test_status_separates_live_offline_error_and_unauthenticated() -> None:
    live = BilibiliLiveSkill(_StateLive({"live": True, "error": ""}))
    assert (json.loads(await live.execute("status", {"room_id": 5440})))["live_state"] == "live"

    offline = BilibiliLiveSkill(_StateLive({"live": False, "error": ""}))
    assert (
        json.loads(await offline.execute("status", {"room_id": 5440}))
    )["live_state"] == "offline"

    broken = BilibiliLiveSkill(
        _StateLive({"live": False, "error": "读取开播状态失败：Timeout"})
    )
    payload = json.loads(await broken.execute("status", {"room_id": 5440}))
    assert payload["live_state"] == "error"
    assert payload["live_error"] == "读取开播状态失败：Timeout"

    service = _DeadService()
    unauth = BilibiliLiveSkill(_StateLive({"live": False, "error": ""}), service=service)
    payload = json.loads(await unauth.execute("status", {"room_id": 5440}))
    assert payload["live_state"] == "unauthenticated"
    assert "登录态已过期" in payload["live_error"]
    assert service.refresh_calls == 1


async def test_enable_parses_auto_reply_flag() -> None:
    live = _EnableLive()
    skill = BilibiliLiveSkill(live)

    await skill.execute("enable", {"room_id": 5440, "auto_reply": "false", "confirm": True})
    await skill.execute("enable", {"room_id": 5440, "auto_reply": "true", "confirm": True})
    await skill.execute("enable", {"room_id": 5440, "confirm": True})

    # "false" 不是真值（旧实现 bool("false") 会当成开）。
    assert [call[1] for call in live.calls] == [False, True, True]
    assert live.started is True


async def test_room_id_validation_and_write_confirm_gate(tmp_path: Path) -> None:
    skill, _interactor, _client = await _skill(tmp_path)

    missing = json.loads(
        await skill.execute("send_danmaku", {"text": "hi", "confirm": True})
    )
    assert missing["ok"] is False and "room_id" in missing["error"]

    blocked = json.loads(
        await skill.execute("send_danmaku", {"room_id": 5440, "text": "hi"})
    )
    assert blocked["ok"] is False and blocked["code"] == "CONFIRM_REQUIRED"

    history = json.loads(await skill.execute("read_history", {"room_id": 5440}))
    assert history["ok"] is True
