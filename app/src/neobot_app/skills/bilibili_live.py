"""BilibiliLiveSkill — B站直播间状态、弹幕、历史、自动回复与定时弹幕。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _room_id(args: dict[str, Any]) -> int:
    try:
        return int(args.get("room_id") or 0)
    except (TypeError, ValueError):
        return 0


class BilibiliLiveSkill(SkillModule):
    """把 BilibiliLiveInteractor 暴露成 agent 工具。"""

    @property
    def name(self) -> str:
        return "bilibili_live"

    @property
    def description(self) -> str:
        return "B站直播间：开播状态、发弹幕、读弹幕历史、自动回复开关与定时弹幕"

    @property
    def instructions(self) -> str:
        return (
            "B站直播 Skill：先 status 查房间是否开播，再 send_danmaku / read_history。\n"
            "所有写操作（发弹幕、定时弹幕）都以当前登录的B站账号发言，且仅在该房间开播时生效；"
            "下播时返回「未开播，不互动」。enable/disable 控制房间监听与自动回复。"
            "需要看画面用 snapshot，需要听一段直播说话用 transcribe（按需，非实时字幕）。"
        )

    def __init__(self, live_interactor: Any = None, service: Any = None) -> None:
        self._live = live_interactor
        self._service = service

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "status",
                "查看B站直播间是否在播、是否已启用、自动回复开关与定时弹幕。不传 room_id 时列出所有已启用房间。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号，可选"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "get_live_willingness",
                "查看直播间回复意愿系数；不传 room_id 时列出全部房间。1.0 表示所有弹幕都回。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号，可选"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "set_live_willingness",
                "设置直播间回复意愿系数（0.0~1.0）；默认 1.0=所有非空弹幕都回。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "value": {"type": "number", "description": "0.0~1.0；0 全不回，1 全回"},
                    },
                    "required": ["room_id", "value"],
                },
            ),
            self._tool_def(
                "remove_live_willingness",
                "移除直播间回复意愿系数，恢复默认所有非空弹幕都回。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "send_danmaku",
                "以当前登录的B站账号在直播间发一条弹幕；仅开播时发送，下播返回未开播不互动。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "text": {"type": "string", "description": "弹幕正文；B站硬限制20字，一句说完，不带QQ群号/客服腔/markdown/@/链接/颜文字"},
                    },
                    "required": ["room_id", "text"],
                },
            ),
            self._tool_def(
                "read_history",
                "读取直播间最近弹幕（最多 50 条，按时间从旧到新）。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "count": {"type": "integer", "description": "读取条数，默认 500（最多 500）", "default": 500},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "enable",
                "启用直播间监听（写操作）。启用后自动回复会以当前B站账号发言。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "auto_reply": {
                            "type": "boolean",
                            "description": "是否自动回复本房间所有非空弹幕，默认 true",
                            "default": True,
                        },
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "disable",
                "停用直播间监听并删除其定时弹幕（写操作）。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "schedule",
                "给已启用直播间加定时弹幕（写操作）：到点且开播时，以当前B站账号发一条口语化弹幕。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "time": {"type": "string", "description": "本地时间 HH:MM"},
                        "recurrence": {
                            "type": "string",
                            "enum": ["once", "daily", "weekly"],
                            "description": "once=只发一次，daily=每天，weekly=每 7 天",
                        },
                        "prompt": {"type": "string", "description": "这条弹幕要说的事或主题"},
                    },
                    "required": ["room_id", "time", "recurrence", "prompt"],
                },
            ),
            self._tool_def(
                "list_schedules",
                "列出定时弹幕；不传 room_id 时列出所有已启用房间。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号，可选"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "delete_schedule",
                "删除一条定时弹幕（写操作）。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "schedule_id": {"type": "string", "description": "list_schedules 返回的任务 ID"},
                    },
                    "required": ["room_id", "schedule_id"],
                },
            ),
            self._tool_def(
                "recent_events",
                "读取直播间最近的礼物/SC/上舰/进房等事件（最多 100 条）。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "count": {"type": "integer", "description": "读取条数，默认 20", "default": 20},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "record_clip",
                "按需录制直播间一小段 FLV（默认 30 秒，最长 300 秒）；仅开播时可用。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "seconds": {"type": "integer", "description": "录制秒数，默认 30，最大 300", "default": 30},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "snapshot",
                "按需获取直播间当前画面的一帧截图；仅开播时可用，返回本地文件路径与可选画面描述。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                    },
                    "required": ["room_id"],
                },
            ),
            self._tool_def(
                "transcribe",
                "按需截取直播间一段音频并做 ASR 转写；仅开播时可用。",
                {
                    "properties": {
                        "room_id": {"type": "integer", "description": "直播间短号或房间号"},
                        "seconds": {"type": "integer", "description": "截取音频秒数，默认 15，建议 10-30", "default": 15},
                    },
                    "required": ["room_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        live = self._live
        if live is None:
            return _json({"ok": False, "error": "B站直播交互器不可用"})
        try:
            if tool_name == "status":
                return await self._status(live, args)
            if tool_name == "get_live_willingness":
                return _json(live.get_live_willingness(_room_id(args)))
            if tool_name == "set_live_willingness":
                rid = _room_id(args)
                if rid <= 0:
                    return _json({"ok": False, "error": "房间号无效"})
                try:
                    value = float(args.get("value"))
                except (TypeError, ValueError):
                    return _json({"ok": False, "error": "value 必须是数字"})
                return _json(live.set_live_willingness(rid, value))
            if tool_name == "remove_live_willingness":
                rid = _room_id(args)
                if rid <= 0:
                    return _json({"ok": False, "error": "房间号无效"})
                return _json(live.remove_live_willingness(rid))
            if tool_name == "send_danmaku":
                return await self._send_danmaku(live, args)
            if tool_name == "read_history":
                return self._read_history(live, args)
            if tool_name == "enable":
                return await self._enable(live, args)
            if tool_name == "disable":
                return await self._disable(live, args)
            if tool_name == "schedule":
                return await self._schedule(live, args)
            if tool_name == "list_schedules":
                return self._list_schedules(live, args)
            if tool_name == "delete_schedule":
                return await self._delete_schedule(live, args)
            if tool_name == "recent_events":
                return self._recent_events(live, args)
            if tool_name == "record_clip":
                return await self._record_clip(live, args)
            if tool_name == "snapshot":
                return await self._snapshot(live, args)
            if tool_name == "transcribe":
                return await self._transcribe(live, args)
        except Exception as exc:
            return _json({"ok": False, "error": f"B站直播操作失败：{type(exc).__name__}: {exc}"})
        return _json({"ok": False, "error": f"未知工具: {tool_name}"})

    async def _status(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        if args.get("room_id") not in (None, "") and rid <= 0:
            return _json({"ok": False, "error": "房间号无效"})
        rooms = {int(item.get("room_id") or 0): item for item in live.list_rooms()}
        if rid <= 0:
            result = []
            for room_id, room in rooms.items():
                result.append(
                    {
                        "room_id": room_id,
                        "name": str(room.get("name") or ""),
                        "auto_reply": bool(room.get("auto_reply")),
                        "asr": bool(room.get("asr", False)),
                        "live": await live.is_live(room_id),
                        "schedules": live.list_schedules(room_id),
                    }
                )
            return _json({"ok": True, "rooms": result})
        room = rooms.get(rid) or {}
        return _json(
            {
                "ok": True,
                "room_id": rid,
                "enabled": rid in rooms,
                "name": str(room.get("name") or ""),
                "auto_reply": bool(room.get("auto_reply", False)),
                "asr": bool(room.get("asr", False)),
                "live": await live.is_live(rid),
                "schedules": live.list_schedules(rid),
            }
        )

    async def _send_danmaku(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        text = str(args.get("text") or "").strip()
        result = await live.send_danmaku(rid, text)
        return _json(
            {
                "ok": bool(result.get("ok")),
                "room_id": rid,
                "text": text,
                "error": str(result.get("error") or ""),
                "note": "将以当前B站账号发言",
            }
        )

    def _read_history(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        if rid <= 0:
            return _json({"ok": False, "error": "房间号无效"})
        try:
            count = int(args.get("count") or 500)
        except (TypeError, ValueError):
            count = 500
        items = live.get_history(rid, count)
        return _json(
            {
                "ok": True,
                "room_id": rid,
                "count": len(items),
                "history": items,
                "display": live.format_history(rid, count),
            }
        )

    def _recent_events(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        try:
            count = max(1, min(int(args.get("count") or 20), 100))
        except (TypeError, ValueError):
            count = 20
        events = live.recent_events(rid, count)
        payload = []
        for event in events or []:
            payload.append(
                {
                    "kind": getattr(event, "kind", ""),
                    "uid": getattr(event, "uid", 0),
                    "name": getattr(event, "name", ""),
                    "text": getattr(event, "text", ""),
                    "value": getattr(event, "value", 0),
                    "ts": getattr(event, "ts", 0),
                }
            )
        return _json({"ok": True, "room_id": rid, "count": len(payload), "events": payload})

    async def _record_clip(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        try:
            seconds = max(5, min(int(args.get("seconds") or 30), 300))
        except (TypeError, ValueError):
            seconds = 30
        result = await live.record_clip(rid, seconds=seconds)
        payload = dict(result)
        payload["note"] = "本地录制文件；仅用于回看/留证，不自动发送"
        return _json(payload)

    async def _snapshot(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        result = await live.snapshot(rid)
        payload = dict(result)
        payload["note"] = "画面文件保存在本机；描述由视觉模型生成，可能不准确"
        return _json(payload)

    async def _transcribe(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        try:
            seconds = max(5, min(int(args.get("seconds") or 15), 60))
        except (TypeError, ValueError):
            seconds = 15
        result = await live.transcribe(rid, seconds=seconds)
        payload = dict(result)
        payload["note"] = "按需截取直播音频转写，不是实时字幕"
        return _json(payload)

    async def _enable(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        await live.ensure_started()
        result = await live.enable(rid, auto_reply=bool(args.get("auto_reply", True)))
        payload = dict(result)
        payload["note"] = "写操作：启用后自动回复将以当前B站账号发言"
        return _json(payload)

    async def _disable(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        result = await live.disable(rid)
        payload = dict(result)
        payload["note"] = "写操作：停用后不再监听该房间"
        return _json(payload)

    async def _schedule(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        result = await live.schedule(
            rid,
            str(args.get("time") or ""),
            str(args.get("recurrence") or ""),
            str(args.get("prompt") or ""),
        )
        payload = dict(result)
        payload["note"] = "写操作：到点将以当前B站账号发弹幕"
        return _json(payload)

    def _list_schedules(self, live: Any, args: dict[str, Any]) -> str:
        raw = args.get("room_id")
        rid = _room_id(args)
        if raw not in (None, "") and rid <= 0:
            return _json({"ok": False, "error": "房间号无效"})
        return _json({"ok": True, "schedules": live.list_schedules(rid or None)})

    async def _delete_schedule(self, live: Any, args: dict[str, Any]) -> str:
        rid = _room_id(args)
        result = await live.delete_schedule(rid, str(args.get("schedule_id") or "").strip())
        payload = dict(result)
        payload["note"] = "写操作：删除后该定时弹幕不再发送"
        return _json(payload)
