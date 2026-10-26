"""定时弹幕的增删查与到点扫描。"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from neobot_app.bilibili.live_parts.constants import _RECURRENCES, _SCHEDULE_CHECK_SECONDS
from neobot_app.bilibili.live_parts.helpers import _normalize_clock, _to_int


class _SchedulesMixin:
    """定时弹幕 CRUD、到点判定与定时循环。"""

    async def schedule(self, room_id: int, time: str, recurrence: str, prompt: str) -> dict[str, Any]:
        """为已启用房间添加定时弹幕；到点且房间在播才发送。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        self._load()
        room = self._rooms.get(str(rid))
        if room is None:
            return {"ok": False, "error": "房间未启用"}
        clock = _normalize_clock(time)
        if clock is None:
            return {"ok": False, "error": "时间格式应为 HH:MM"}
        rec = str(recurrence or "").strip().lower()
        if rec not in _RECURRENCES:
            return {"ok": False, "error": "recurrence 只能是 once/daily/weekly"}
        text = str(prompt or "").strip()
        if not text:
            return {"ok": False, "error": "prompt 不能为空"}
        record = {
            "id": uuid4().hex[:12],
            "time": clock,
            "recurrence": rec,
            "prompt": text,
            "last_fired_date": "",
        }
        if rec == "weekly":
            # 每周规则按星期几：以创建当天为准，错过一周也只等下一个同样的星期几。
            record["weekday"] = datetime.now().astimezone().weekday()
        room.setdefault("schedules", []).append(record)
        self._save()
        self._logger.info(
            f"B站直播定时弹幕已创建：房间 {rid}，任务 {record['id']}，"
            f"时间 {clock}，周期 {rec}"
        )
        return {"ok": True, "room_id": rid, "schedule": dict(record)}

    def list_schedules(self, room_id: int | None = None) -> list[dict[str, Any]]:
        """列出定时弹幕；room_id 为空时列出所有已启用房间。"""
        self._load()
        if room_id is None:
            room_ids = sorted(self._rooms, key=_to_int)
        else:
            rid = _to_int(room_id)
            room_ids = [str(rid)] if str(rid) in self._rooms else []
        items: list[dict[str, Any]] = []
        for key in room_ids:
            rid = _to_int(key)
            for record in self._rooms[key].get("schedules") or []:
                items.append({"room_id": rid, **record})
        return items

    async def delete_schedule(self, room_id: int, schedule_id: str) -> dict[str, Any]:
        """删除一条定时弹幕。"""
        rid = _to_int(room_id)
        sid = str(schedule_id or "").strip()
        if rid <= 0 or not sid:
            return {"ok": False, "error": "房间号或定时任务 ID 不能为空"}
        self._load()
        room = self._rooms.get(str(rid))
        if room is None:
            return {"ok": False, "error": "房间未启用"}
        schedules = room.get("schedules") or []
        kept = [item for item in schedules if str(item.get("id")) != sid]
        if len(kept) == len(schedules):
            return {"ok": False, "error": "定时弹幕不存在"}
        room["schedules"] = kept
        self._save()
        self._logger.info(f"B站直播定时弹幕已删除：房间 {rid}，任务 {sid}")
        return {"ok": True, "room_id": rid, "schedule_id": sid}

    async def _schedule_loop(self) -> None:
        while self._running:
            try:
                await self._scan_schedules()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.warning(
                    f"B站直播定时弹幕检查失败：{type(exc).__name__}: {exc}"
                )
            await asyncio.sleep(_SCHEDULE_CHECK_SECONDS)

    @staticmethod
    def _is_schedule_due(schedule: dict[str, Any], now: datetime) -> bool:
        """到点判定：>= HH:MM 且本时段未发过；不再要求恰好在那一分钟检查。"""
        clock = str(schedule.get("time") or "")
        if not clock or now.strftime("%H:%M") < clock:
            return False
        last = str(schedule.get("last_fired_date") or "")
        recurrence = str(schedule.get("recurrence") or "")
        if recurrence == "once":
            return not last
        if recurrence == "daily":
            return last != now.date().isoformat()
        if recurrence == "weekly":
            return now.weekday() == _SchedulesMixin._schedule_weekday(schedule, now) and (
                last != now.date().isoformat()
            )
        return False

    @staticmethod
    def _schedule_weekday(schedule: dict[str, Any], now: datetime) -> int:
        """每周规则的星期几：优先存下来的 weekday，其次上次执行日期，兜底今天。"""
        value = schedule.get("weekday")
        if isinstance(value, int) and 0 <= value <= 6:
            return value
        try:
            return date.fromisoformat(str(schedule.get("last_fired_date") or "")).weekday()
        except ValueError:
            return now.weekday()

    async def _scan_schedules(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """检查到点的定时弹幕：daily/weekly 到点即消耗本时段，once 发送成功后才落盘。"""
        current = now or datetime.now().astimezone()
        fired: list[dict[str, Any]] = []
        for room_id, room in list(self._rooms.items()):
            for schedule in list(room.get("schedules") or []):
                if not self._is_schedule_due(schedule, current):
                    continue
                rid = _to_int(room_id)
                recurrence = str(schedule.get("recurrence") or "")
                # daily/weekly 到点即消耗本时段：下播/失败都不在同一时段重试；
                # once 是唯一的一条，失败不落盘，等下一次检查再试。
                if recurrence != "once":
                    schedule["last_fired_date"] = current.date().isoformat()
                    self._save()
                if not await self.is_live(rid):
                    self._logger.info(
                        f"B站直播间未开播，跳过定时弹幕：房间 {room_id}，任务 {schedule.get('id')}"
                    )
                    continue
                texts = await self._generate_schedule_danmaku(
                    str(schedule.get("prompt") or ""),
                    self.format_history(rid, 50),
                    rid,
                )
                if not texts:
                    continue
                client = self._get_client()
                if client is None:
                    continue
                sent = True
                for text in texts:
                    if not await self._post_danmaku(
                        client, rid, text, action="定时弹幕"
                    ):
                        sent = False
                        break
                if not sent:
                    continue
                if recurrence == "once":
                    schedule["last_fired_date"] = current.date().isoformat()
                    self._save()
                fired.append(
                    {
                        "room_id": rid,
                        "schedule_id": schedule.get("id"),
                        "text": text,
                    }
                )
                self._logger.info(
                    f"B站直播已发送定时弹幕：房间 {room_id}，"
                    f"任务 {schedule.get('id')}，{len(text)} 字"
                )
        return fired
