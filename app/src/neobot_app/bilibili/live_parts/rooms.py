"""启用房间、开播状态、弹幕历史与状态文件读写。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.bilibili.live_parts.constants import (
    _LIVE_STATUS_TTL_SECONDS,
    _MAX_HISTORY,
    _MAX_RECENT_EVENTS,
)
from neobot_app.bilibili.live_parts.helpers import _normalize_schedule, _to_int
from neobot_app.bilibili.live_protocol import LiveEvent
from neobot_app.bilibili.prompts import MAX_LIVE_DANMAKU_CHARS
from neobot_app.utils.atomic import atomic_write_text


class _RoomsMixin:
    """房间管理、开播状态/历史读取与 <DATA_DIR>/bilibili/live_interact.json 读写。"""

    async def enable(self, room_id: int, *, auto_reply: bool = True) -> dict[str, Any]:
        """启用房间并写入状态；未登录/不可用直接失败，不出"监听已开"的假成功。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        client = self._get_client()
        if client is None:
            return {"ok": False, "error": "B站未登录或客户端不可用，暂时无法监听直播间"}
        self._load()
        await self._resolve_my_uid(client)
        data: dict[str, Any] = {}
        try:
            data = await call_client(client.get_live_room_info, rid) or {}
        except Exception as exc:
            self._logger.warning(
                f"B站直播间信息读取失败，先按输入房间号启用：房间 {rid}，"
                f"错误 {type(exc).__name__}: {exc}"
            )
        room_info = data.get("room_info") if isinstance(data, dict) else None
        anchor = data.get("anchor_info") if isinstance(data, dict) else None
        base_info = anchor.get("base_info") if isinstance(anchor, dict) else None
        existing = self._rooms.get(str(rid)) or {}
        # 接口失败时保留上次的真实房间号/主播名，不要用输入值把已知信息覆盖成空。
        real_room_id = (
            (_to_int(room_info.get("room_id")) if isinstance(room_info, dict) else 0)
            or _to_int(existing.get("real_room_id"))
            or rid
        )
        name = (
            str(base_info.get("uname") or "") if isinstance(base_info, dict) else ""
        ) or str(existing.get("name") or "")
        room = {
            "real_room_id": real_room_id,
            "name": name,
            "auto_reply": bool(auto_reply),
            "asr": bool(existing.get("asr", self._asr_default_enabled)),
            # 重新启用不应丢掉已配置的定时弹幕。
            "schedules": list(existing.get("schedules") or []),
        }
        self._rooms[str(rid)] = room
        self._save()
        self._start_task(str(rid))
        self._logger.info(f"B站直播房间已启用：房间 {rid}，自动回复{'开' if room['auto_reply'] else '关'}")
        return {
            "ok": True,
            "room_id": rid,
            "real_room_id": real_room_id,
            "name": name,
            "auto_reply": room["auto_reply"],
            "asr": room["asr"],
        }

    async def disable(self, room_id: int) -> dict[str, Any]:
        """停用房间并删除持久化状态。"""
        rid = _to_int(room_id)
        self._load()
        removed = self._rooms.pop(str(rid), None) is not None
        await self._cancel_task(str(rid))
        if removed:
            self._save()
            self._logger.info(f"B站直播房间已停用：房间 {rid}")
        return {"ok": removed, "room_id": rid}

    def list_rooms(self) -> list[dict[str, Any]]:
        """已启用的房间列表（按房间号排序）。"""
        self._load()
        rooms = []
        for room_id in sorted(self._rooms, key=_to_int):
            room = self._rooms[room_id]
            rooms.append(
                {
                    "room_id": _to_int(room_id),
                    "real_room_id": _to_int(room.get("real_room_id")) or _to_int(room_id),
                    "name": str(room.get("name") or ""),
                    "auto_reply": bool(room.get("auto_reply", True)),
                    "asr": bool(room.get("asr", self._asr_default_enabled)),
                }
            )
        return rooms

    async def set_auto_reply(self, room_id: int, on: bool) -> dict[str, Any]:
        """开关已启用房间的自动回复（不影响 WebSocket 监听）。"""
        rid = _to_int(room_id)
        self._load()
        room = self._rooms.get(str(rid))
        if room is None:
            return {"ok": False, "error": "房间未启用"}
        room["auto_reply"] = bool(on)
        self._save()
        return {"ok": True, "room_id": rid, "auto_reply": room["auto_reply"]}

    async def set_asr(self, room_id: int, on: bool) -> dict[str, Any]:
        """开关已启用房间的自动 ASR 上下文（默认打开）。"""
        rid = _to_int(room_id)
        self._load()
        room = self._rooms.get(str(rid))
        if room is None:
            return {"ok": False, "error": "房间未启用"}
        room["asr"] = bool(on)
        self._save()
        return {"ok": True, "room_id": rid, "asr": room["asr"]}

    async def send_danmaku(self, room_id: int, text: str) -> dict[str, Any]:
        """手动发一条直播弹幕（不受自动回复开关影响；下播时不发送）。"""
        rid = _to_int(room_id)
        message = str(text or "").strip()
        if rid <= 0 or not message:
            return {"ok": False, "error": "房间号或弹幕内容不能为空"}
        if len(message) > MAX_LIVE_DANMAKU_CHARS:
            return {"ok": False, "error": f"弹幕超过 {MAX_LIVE_DANMAKU_CHARS} 字，已拦截"}
        client = self._get_client()
        if client is None:
            return {"ok": False, "error": "B站未登录或客户端不可用"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不互动"}
        try:
            sent = await call_client(client.send_danmaku, rid, message)
        except Exception as exc:
            self._logger.warning(
                f"B站直播弹幕发送失败：房间 {rid}，错误 {type(exc).__name__}: {exc}"
            )
            return {"ok": False, "error": "B站直播弹幕发送失败"}
        if not sent:
            return {"ok": False, "error": "B站直播弹幕发送失败"}
        return {"ok": True, "error": ""}

    # ── 开播状态与房间历史 ──

    async def live_status(self, room_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """房间开播三态：{live: True, error: ""} 在播；{False, ""} 明确未开播；
        {False, 非空 error} 接口不可用（未登录/网络/返回异常，不写缓存）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"live": False, "error": "房间号无效"}
        key = str(rid)
        now = time.monotonic()
        cached = self._live_cache.get(key)
        if not refresh and cached is not None and now - cached[0] < _LIVE_STATUS_TTL_SECONDS:
            return {"live": cached[1], "error": ""}
        client = self._get_client()
        if client is None:
            return {"live": False, "error": "B站未登录或客户端不可用"}
        try:
            data = await call_client(client.get_live_room_info, rid)
        except Exception as exc:
            self._logger.warning(
                f"B站直播间开播状态读取失败：房间 {rid}，错误 {type(exc).__name__}: {exc}"
            )
            return {"live": False, "error": f"读取开播状态失败：{type(exc).__name__}"}
        room_info = data.get("room_info") if isinstance(data, dict) else None
        if not isinstance(room_info, dict):
            # client 读失败时返回空 dict；这时不能当成"没开播"，也不写缓存。
            return {"live": False, "error": "读取开播状态失败：接口未返回直播间信息"}
        live = _to_int(get_field(room_info, "live_status", 0)) == 1
        self._live_cache[key] = (now, live)
        return {"live": live, "error": ""}

    async def is_live(self, room_id: int, *, refresh: bool = False) -> bool:
        """兼容包装：接口不可用时按未开播处理；需要区分三态的调用方用 live_status。"""
        return bool((await self.live_status(room_id, refresh=refresh)).get("live"))

    def get_history(self, room_id: int, count: int = _MAX_HISTORY) -> list[dict[str, Any]]:
        """房间最近弹幕（旧→新），默认最多 500 条。"""
        rid = _to_int(room_id)
        limit = max(1, min(_to_int(count) or _MAX_HISTORY, _MAX_HISTORY))
        items = self._history.get(str(rid))
        if not items:
            return []
        return [dict(item) for item in list(items)[-limit:]]

    def recent_events(self, room_id: int, count: int = 20) -> list[LiveEvent]:
        """房间最近的礼物/SC/上舰/进房等事件（旧→新，最多 100 条）。"""
        rid = _to_int(room_id)
        limit = max(1, min(_to_int(count) or 20, _MAX_RECENT_EVENTS))
        items = self._recent.get(str(rid))
        return list(items)[-limit:] if items else []

    def format_history(self, room_id: int, count: int = _MAX_HISTORY) -> str:
        """按群聊风格渲染弹幕：每行带时间，超过 5 分钟间隔插时间线。"""
        items = self.get_history(room_id, count)
        lines: list[str] = []
        last_ts = 0.0
        for item in items:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            ts = float(item.get("ts") or 0.0)
            clock = str(item.get("time") or "")
            if ts and last_ts and ts - last_ts >= 300:
                lines.append(f"--- {datetime.fromtimestamp(ts).strftime('%H:%M')} ---")
            name = str(item.get("name") or "观众")
            uid = _to_int(item.get("uid"))
            prefix = f"[uid={uid}] " if uid else ""
            if item.get("at_me"):
                prefix = "[@了我] " + prefix
            lines.append(f"[{clock}] {prefix}{name}: {text}")
            if ts:
                last_ts = ts
        return "\n".join(lines)

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            # 状态文件坏了：先备份再按空状态启动，绝不能拿空房间表把用户配置覆盖掉。
            backup = self._path.with_name(self._path.name + ".bad")
            try:
                self._path.replace(backup)
            except OSError as backup_exc:
                self._state_broken = True
                self._logger.error(
                    f"B站直播交互状态文件解析失败且备份失败，本次不会覆盖原文件："
                    f"错误 {type(exc).__name__}: {exc}；"
                    f"备份错误 {type(backup_exc).__name__}: {backup_exc}"
                )
                return
            self._logger.error(
                f"B站直播交互状态文件解析失败，已备份为 {backup.name}：{type(exc).__name__}: {exc}"
            )
            return
        rooms = raw.get("rooms") if isinstance(raw, dict) else None
        if not isinstance(rooms, dict):
            return
        for key, value in rooms.items():
            room_id = _to_int(key)
            if room_id <= 0 or not isinstance(value, dict):
                continue
            schedules = []
            for raw in value.get("schedules") or []:
                schedule = _normalize_schedule(raw)
                if schedule is not None:
                    schedules.append(schedule)
            self._rooms[str(room_id)] = {
                "real_room_id": _to_int(value.get("real_room_id")) or room_id,
                "name": str(value.get("name") or ""),
                "auto_reply": bool(value.get("auto_reply", True)),
                "asr": bool(value.get("asr", self._asr_default_enabled)),
                "schedules": schedules,
            }

    def _save(self) -> None:
        if self._state_broken:
            self._logger.warning("B站直播交互状态文件损坏且备份失败，本次不写盘以免覆盖原配置")
            return
        rooms: dict[str, dict[str, Any]] = {}
        for room_id, room in sorted(self._rooms.items(), key=lambda item: _to_int(item[0])):
            entry: dict[str, Any] = {
                "real_room_id": _to_int(room.get("real_room_id")) or _to_int(room_id),
                "name": str(room.get("name") or ""),
                "auto_reply": bool(room.get("auto_reply", True)),
                "asr": bool(room.get("asr", self._asr_default_enabled)),
            }
            schedules = [dict(item) for item in room.get("schedules") or []]
            if schedules:
                entry["schedules"] = schedules
            rooms[room_id] = entry
        payload = {"rooms": rooms}
        try:
            atomic_write_text(self._path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            self._logger.warning(f"B站直播交互状态保存失败：{type(exc).__name__}: {exc}")
