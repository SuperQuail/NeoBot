"""B站直播弹幕交互器 — 独立于 streaming_parser 插件的直播监听。

一个实例管理多个直播间：用 BilibiliClient 的直播 HTTP 接口拿 token/host_list，
再连 B站弹幕 WebSocket（`wss://host:wss_port/sub`）收 DANMU_MSG，按需调用
provider 生成一句极短回复，再由 BilibiliClient.send_danmaku 发出。

只参与开播阶段：房间 live_status 缓存 60 秒，回复意愿按 QQ 群聊同一套公式计算（@ 必回、基础概率、全局/会话/用户系数），再加 cooldown；
下播时 WSS 可以继续收弹幕（保留历史），但不生成、不发送。

启用房间与定时弹幕持久化在 `<DATA_DIR>/bilibili/live_interact.json`；
每个房间保留最近 500 条弹幕供 agent / 跨聊天读取（带时间标记），另有 100 条
礼物/SC/上舰/进房事件供 recent_events() 读取，并可通过 on_event 回调实时发出。
start() 恢复连接与定时循环。
不 import streaming_parser，也不依赖它的订阅/轮询。
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiohttp

from neobot_app.bilibili._compat import RecentIds, call_client, get_field, resolve_client
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.bilibili.live_protocol import (
    LiveEvent,
    check_auth_reply,
    decode_packets,
    encode_packet,
    event_key,
    parse_danmu_message,
    parse_events,
)
from neobot_app.bilibili.prompts import (
    MAX_LIVE_DANMAKU_CHARS,
    LiveDanmakuContext,
    build_live_danmaku_prompt,
    build_live_observation_prompt,
    build_live_scheduled_prompt,
)
from neobot_app.bilibili.tool_reply import ToolReply, run_tool_reply
from neobot_app.core import DATA_DIR
from neobot_app.utils.atomic import atomic_write_text
from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.logging import Logger

__all__ = ("BilibiliLiveInteractor", "decode_packets", "encode_packet", "parse_danmu_message")

_LOGGER = get_module_logger("bilibili.live_interact")

_WS_OP_HEARTBEAT = 2
_WS_OP_MESSAGE = 5
_WS_OP_AUTH = 7
_WS_OP_AUTH_REPLY = 8
_WS_HEARTBEAT_SECONDS = 30.0
_WS_RECONNECT_MAX_SECONDS = 60.0
_WS_HEALTHY_SECONDS = 60.0
#: 单房间每分钟最多自动回复条数（冷却之外的硬上限）。
_MAX_REPLIES_PER_MINUTE = 3
_REPLY_WINDOW_SECONDS = 60.0
#: 房间开播状态缓存时长；避免每条弹幕都打一次直播间信息接口。
_LIVE_STATUS_TTL_SECONDS = 60.0
#: 每房间保留的最近弹幕条数。
_MAX_HISTORY = 500
#: 每房间保留的最近非弹幕事件条数。
_MAX_RECENT_EVENTS = 100
#: 直播间复用 QQ 档案表；加前缀避免与 QQ 群号/QQ 号撞键。
_LIVE_ROOM_ARCHIVE_PREFIX = "bilibili_live:room:"
_LIVE_USER_ARCHIVE_PREFIX = "bilibili_live:uid:"
#: 跨房间事件去重键容量。
_MAX_EVENT_KEYS = 2000
#: 定时弹幕检查间隔。
_SCHEDULE_CHECK_SECONDS = 30.0
_RECURRENCES = frozenset({"once", "daily", "weekly"})


class BilibiliLiveInteractor:
    """多房间直播弹幕监听 + 可选自动回复。"""

    def __init__(
        self,
        service: Any = None,
        *,
        provider: Any = None,
        bot_name: str = "",
        bot_data: str = "",
        data_dir: Path | None = None,
        logger: Logger | None = None,
        cooldown_seconds: float = 5.0,
        max_reply_chars: int = MAX_LIVE_DANMAKU_CHARS,
        at_only: bool = True,
        asr_service: Any = None,
        vision_provider: Any = None,
        media_service: Any = None,
        on_event: Callable[[LiveEvent], Any] | None = None,
        willing_service: Any = None,
        flow_registry: Any = None,
        mention_names: Any = None,
        reply_chance: float = 0.5,
        asr_default_enabled: bool = False,
        prompt_store: Any = None,
        auto_look_enabled: bool = False,
        auto_look_interval_minutes: int = 30,
        screenshot_replies: bool = False,
        archive_service: Any = None,
        summary_every: int = 200,
    ) -> None:
        # service 可以是 BilibiliService 或 BilibiliClient；每轮用 resolve_client 取当前 client。
        self._service = service
        self._provider = provider
        self._bot_name = str(bot_name or "").strip().lstrip("@")
        self._bot_data = str(bot_data or "").strip()
        base_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self._path = base_dir / "bilibili" / "live_interact.json"
        self._logger = logger or _LOGGER
        self._cooldown = max(0.0, float(cooldown_seconds or 0.0))
        self._max_reply_chars = min(
            MAX_LIVE_DANMAKU_CHARS, max(1, int(max_reply_chars or MAX_LIVE_DANMAKU_CHARS))
        )
        self._at_only = bool(at_only)
        self._asr_service = asr_service
        self._vision_provider = vision_provider
        self._media: Any = media_service
        if self._media is None:
            try:
                from .live_media import LiveMediaService

                self._media = LiveMediaService(
                    self._service,
                    asr_service=asr_service,
                    logger=self._logger,
                    data_dir=base_dir,
                )
            except Exception:
                self._media = None
        self._rooms: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._reply_times: dict[str, deque[float]] = defaultdict(deque)
        self._last_reply_at: dict[str, float] = {}
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._recent: dict[str, deque[LiveEvent]] = {}
        self._event_keys = RecentIds(_MAX_EVENT_KEYS)
        self._event_tasks: set[asyncio.Task[None]] = set()
        self._on_event = on_event
        self._willing_service = willing_service
        self._flow_registry = flow_registry
        self._mention_names = tuple(
            str(name).strip() for name in (mention_names or ()) if str(name).strip()
        )
        self._reply_chance = max(0.0, min(1.0, float(reply_chance or 0.5)))
        self._asr_default_enabled = bool(asr_default_enabled)
        self._prompt_store = prompt_store
        self._auto_look_enabled = bool(auto_look_enabled)
        self._auto_look_interval_minutes = max(5, int(auto_look_interval_minutes or 30))
        self._screenshot_replies = bool(screenshot_replies)
        self._archive_service = archive_service
        self._summary_every = max(0, int(summary_every or 0))
        self._summary_counts: dict[str, int] = defaultdict(int)
        self._room_memory: dict[str, str] = {}
        self._user_memory: dict[int, str] = {}
        self._user_memory_tasks: set[asyncio.Task[None]] = set()
        self._user_archive_seen: set[int] = set()
        self._summary_tasks: set[asyncio.Task[None]] = set()
        self._last_auto_look = time.monotonic()
        self._live_cache: dict[str, tuple[float, bool]] = {}
        self._schedule_task: asyncio.Task[None] | None = None
        self._auto_look_task: asyncio.Task[None] | None = None
        self._reply_locks: dict[str, asyncio.Lock] = {}
        self._reply_tasks: set[asyncio.Task[None]] = set()
        self._loaded = False
        self._running = False

    # ── 生命周期 ──

    async def start(self) -> None:
        """读取持久化房间并为每个房间启动监听任务；失败只记日志。"""
        if self._running:
            return
        self._load()
        self._running = True
        for room_id in list(self._rooms):
            self._start_task(room_id)
        await self._load_live_summaries()
        if self._schedule_task is None or self._schedule_task.done():
            self._schedule_task = asyncio.create_task(self._schedule_loop(), name="bilibili-live-schedules")
        if self._auto_look_enabled and (self._auto_look_task is None or self._auto_look_task.done()):
            self._auto_look_task = asyncio.create_task(
                self._auto_look_loop(), name="bilibili-live-auto-look"
            )
        self._logger.info(f"B站直播交互器已启动：房间数 {len(self._rooms)}")

    async def ensure_started(self) -> None:
        """监听器没在运行时拉起（登录、命令开启前调用）；幂等。"""
        if self._running:
            return
        await self.start()

    async def stop(self) -> None:
        """停止所有监听任务；持久化状态保留，下次 start() 恢复。"""
        self._running = False
        tasks = list(self._tasks.items())
        self._tasks.clear()
        schedule_task = self._schedule_task
        self._schedule_task = None
        auto_look_task = self._auto_look_task
        self._auto_look_task = None
        event_tasks = list(self._event_tasks)
        self._event_tasks.clear()
        reply_tasks = list(self._reply_tasks)
        self._reply_tasks.clear()
        summary_tasks = list(self._summary_tasks)
        self._summary_tasks.clear()
        for _room_id, task in tasks:
            task.cancel()
        if schedule_task is not None:
            schedule_task.cancel()
        if auto_look_task is not None:
            auto_look_task.cancel()
        for task in event_tasks:
            task.cancel()
        for task in reply_tasks:
            task.cancel()
        for task in summary_tasks:
            task.cancel()
        for _room_id, task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if schedule_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await schedule_task
        if auto_look_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await auto_look_task
        for task in event_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in reply_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in summary_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._logger.info("B站直播交互器已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 房间管理 ──

    async def enable(self, room_id: int, *, auto_reply: bool = True) -> dict[str, Any]:
        """启用房间并写入状态；拿到房间信息时补真实房间号/主播名。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        self._load()
        data: dict[str, Any] = {}
        client = self._get_client()
        if client is not None:
            try:
                data = await call_client(client.get_live_room_info, rid) or {}
            except Exception as exc:
                self._logger.warning(
                    "B站直播间信息读取失败，先按输入房间号启用",
                    room_id=rid,
                    error=f"{type(exc).__name__}: {exc}",
                )
        room_info = data.get("room_info") if isinstance(data, dict) else None
        real_room_id = (_to_int(room_info.get("room_id")) if isinstance(room_info, dict) else 0) or rid
        anchor = data.get("anchor_info") if isinstance(data, dict) else None
        base_info = anchor.get("base_info") if isinstance(anchor, dict) else None
        name = str(base_info.get("uname") or "") if isinstance(base_info, dict) else ""
        existing = self._rooms.get(str(rid)) or {}
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
        self._logger.info(
            f"B站直播房间已启用：房间 {rid}，自动回复{'开' if room['auto_reply'] else '关'}"
        )
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
                "B站直播弹幕发送失败",
                room_id=rid,
                error=f"{type(exc).__name__}: {exc}",
            )
            return {"ok": False, "error": "B站直播弹幕发送失败"}
        if not sent:
            return {"ok": False, "error": "B站直播弹幕发送失败"}
        return {"ok": True, "error": ""}

    # ── 开播状态与房间历史 ──

    async def is_live(self, room_id: int, *, refresh: bool = False) -> bool:
        """房间是否在播；live_status 缓存 60 秒，接口不可用时按未开播处理。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return False
        key = str(rid)
        now = time.monotonic()
        cached = self._live_cache.get(key)
        if not refresh and cached is not None and now - cached[0] < _LIVE_STATUS_TTL_SECONDS:
            return cached[1]
        live = False
        client = self._get_client()
        if client is not None:
            try:
                data = await call_client(client.get_live_room_info, rid)
            except Exception as exc:
                self._logger.warning(
                    "B站直播间开播状态读取失败",
                    room_id=rid,
                    error=f"{type(exc).__name__}: {exc}",
                )
                data = {}
            room_info = data.get("room_info") if isinstance(data, dict) else None
            live = _to_int(get_field(room_info, "live_status", 0)) == 1
        self._live_cache[key] = (now, live)
        return live

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

    async def frame_context(self, room_id: int) -> str:
        """抓当前直播画面并让视觉模型描述；失败返回空串，不阻断回复。"""
        # 没有视觉模型时截图无人消费，跳过；按需 snapshot 仍可单独调用。
        if self._vision_provider is None:
            return ""
        snapshot = await self.snapshot(room_id)
        if not snapshot.get("ok"):
            return ""
        return str(snapshot.get("description") or "").strip()

    async def snapshot(self, room_id: int) -> dict[str, Any]:
        """按需抓一帧直播画面（返回 path/描述；仅开播时）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不获取画面"}
        try:
            result = await call_client(self._media.capture_frame, rid)
        except Exception as exc:
            self._logger.warning("直播截帧失败", room_id=rid, error=f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"截帧失败：{exc}"}
        if not isinstance(result, dict) or not result.get("ok"):
            return result if isinstance(result, dict) else {"ok": False, "error": "截帧失败"}
        description = await self._describe_frame(result)
        if description:
            result["description"] = description
        return result

    async def record_clip(self, room_id: int, *, seconds: int = 30) -> dict[str, Any]:
        """按需录制一小段直播流（默认 30 秒，最长 300 秒）；仅开播时。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不录制"}
        try:
            return await call_client(self._media.record_clip, rid, seconds=seconds)
        except Exception as exc:
            self._logger.warning("直播录制失败", room_id=rid, error=f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"直播录制失败：{exc}"}

    async def transcribe(self, room_id: int, *, seconds: int = 15) -> dict[str, Any]:
        """按需截取一段直播音频并转写（仅开播时）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不转写"}
        try:
            return await call_client(self._media.transcribe, rid, seconds=seconds)
        except Exception as exc:
            self._logger.warning("直播 ASR 失败", room_id=rid, error=f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"直播转写失败：{exc}"}

    async def _describe_frame(self, snapshot: dict[str, Any]) -> str:
        if self._vision_provider is None:
            return ""
        try:
            raw = snapshot.get("bytes")
            if not raw:
                path = snapshot.get("path")
                if not path:
                    return ""
                raw = await asyncio.to_thread(Path(path).read_bytes)
            from neobot_app.image.parser import _build_vision_image_part

            part = _build_vision_image_part(bytes(raw), logger=self._logger)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "这是B站直播间的当前画面截图。用一两句话客观描述画面里发生了什么，供弹幕回复参考；不要编造看不清的细节。",
                        },
                        part,
                    ],
                }
            ]
            response = self._vision_provider.chat(messages)
            if inspect.isawaitable(response):
                response = await response
            content = response.get("content", "") if isinstance(response, dict) else get_field(response, "content", "")
            return str(content or "").strip()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.debug("直播画面描述失败", error=f"{type(exc).__name__}: {exc}")
            return ""

    # ── 定时弹幕 ──

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
        room.setdefault("schedules", []).append(record)
        self._save()
        self._logger.info(
            "B站直播定时弹幕已创建",
            room_id=rid,
            schedule_id=record["id"],
            time=clock,
            recurrence=rec,
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
        self._logger.info("B站直播定时弹幕已删除", room_id=rid, schedule_id=sid)
        return {"ok": True, "room_id": rid, "schedule_id": sid}

    # ── WebSocket ──

    async def _room_loop(self, room_id: str) -> None:
        backoff = 1.0
        attempt = 0
        while self._running:
            started = time.monotonic()
            try:
                await self._connect_once(room_id, attempt)
                if time.monotonic() - started >= _WS_HEALTHY_SECONDS:
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.warning(
                    f"B站直播弹幕连接失败，准备重连：房间 {room_id}，"
                    f"错误 {type(exc).__name__}: {exc}"
                )
            if not self._running:
                return
            # host_list 按尝试次数轮换，避免一直撞同一个故障节点。
            attempt += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _WS_RECONNECT_MAX_SECONDS)

    async def _connect_once(self, room_id: str, attempt: int = 0) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("B站未登录或客户端不可用")
        rid = _to_int(room_id)
        room = self._rooms.get(room_id) or {}
        real_room_id = _to_int(room.get("real_room_id")) or rid
        info = await call_client(client.get_live_danmu_info, rid)
        if not isinstance(info, dict):
            raise RuntimeError("弹幕服务器信息为空")
        token = str(info.get("token") or "")
        hosts = [item for item in info.get("host_list") or [] if isinstance(item, dict) and item.get("host")]
        if not token or not hosts:
            raise RuntimeError("弹幕服务器信息缺少 token/host_list")
        server = hosts[attempt % len(hosts)]
        host = str(server["host"])
        port = _to_int(server.get("wss_port")) or 443
        url = f"wss://{host}:{port}/sub"
        uid = _to_int(get_field(client, "my_uid", 0))
        buvid = str(get_field(client, "buvid3", "") or get_field(client, "_buvid3", "") or "")
        auth = {
            "uid": uid,
            "roomid": real_room_id,
            "protover": 3,
            "platform": "web",
            "type": 2,
            "buvid": buvid,
            "key": token,
        }
        # token 与 UA 绑定：与 getDanmuInfo 用同一个 UA。
        headers = {
            "User-Agent": _client_user_agent(client),
            "Origin": "https://live.bilibili.com",
            "Referer": f"https://live.bilibili.com/{real_room_id}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, headers=headers) as ws:
                await ws.send_bytes(encode_packet(_WS_OP_AUTH, json.dumps(auth).encode("utf-8")))
                heartbeat = asyncio.create_task(self._heartbeat(ws))
                try:
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.BINARY:
                            for op, body in decode_packets(message.data):
                                if await self._handle_packet(room_id, op, body):
                                    # 认证成功后立即补一次心跳，随后交给 30s 定时器。
                                    await ws.send_bytes(encode_packet(_WS_OP_HEARTBEAT))
                        elif message.type in (
                            aiohttp.WSMsgType.ERROR,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                        ):
                            break
                finally:
                    heartbeat.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat

    @staticmethod
    async def _heartbeat(ws: Any) -> None:
        while True:
            await asyncio.sleep(_WS_HEARTBEAT_SECONDS)
            try:
                await ws.send_bytes(encode_packet(_WS_OP_HEARTBEAT))
            except Exception:
                return

    async def _handle_packet(self, room_id: str, op: int, body: bytes) -> bool:
        """处理一个业务包；返回 True 表示认证成功，需要立即补心跳。"""
        if op == _WS_OP_AUTH_REPLY:
            check_auth_reply(body)
            return True
        if op != _WS_OP_MESSAGE or not body:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        for event in parse_events(payload, _to_int(room_id)):
            if event.kind == "danmaku":
                # 生成回复可能耗时 90s；不能阻塞 WebSocket 收包，否则后续弹幕
                # 连历史都记不上。
                task = asyncio.create_task(
                    self._handle_danmu(
                        room_id,
                        {
                            "uid": event.uid,
                            "name": event.name,
                            "text": event.text,
                            "reply_mid": getattr(event, "reply_mid", 0),
                            "dmid": getattr(event, "dmid", ""),
                        },
                    )
                )
                self._reply_tasks.add(task)
                task.add_done_callback(self._reply_tasks.discard)
                continue
            await self._handle_event(room_id, event)
        return False

    async def _handle_event(self, room_id: str, event: LiveEvent) -> None:
        """统一事件入口：弹幕走历史/自动回复，其余进 recent_events + on_event。"""
        if event.kind == "danmaku":
            await self._handle_danmu(room_id, {"uid": event.uid, "name": event.name, "text": event.text})
            return
        key = event_key(event)
        if key and not self._event_keys.add(f"{room_id}:{key}"):
            return
        events = self._recent.get(room_id)
        if events is None:
            events = self._recent[room_id] = deque(maxlen=_MAX_RECENT_EVENTS)
        events.append(event)
        self._emit_event(event)

    def _emit_event(self, event: LiveEvent) -> None:
        """把事件交给可选回调；异步回调只排任务，不阻塞收包。"""
        if self._on_event is None:
            return
        try:
            result = self._on_event(event)
        except Exception as exc:
            self._logger.warning(f"B站直播事件回调失败：错误 {type(exc).__name__}: {exc}")
            return
        if inspect.isawaitable(result):
            task = asyncio.create_task(self._await_event_callback(result))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_tasks.discard)

    async def _await_event_callback(self, awaitable: Any) -> None:
        try:
            await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"B站直播事件回调失败：错误 {type(exc).__name__}: {exc}")

    # ── 自动回复 ──

    async def _handle_danmu(self, room_id: str, danmu: dict[str, Any]) -> None:
        room_id = str(room_id)
        self._record_history(room_id, danmu)
        _uid = _to_int(danmu.get("uid"))
        if _uid and _uid not in self._user_archive_seen:
            task = asyncio.create_task(
                self._ensure_user_archive(_uid, str(danmu.get("name") or ""))
            )
            self._user_memory_tasks.add(task)
            task.add_done_callback(self._user_memory_tasks.discard)
        lock = self._reply_locks.get(room_id)
        if lock is None:
            lock = self._reply_locks[room_id] = asyncio.Lock()
        async with lock:
            await self._process_danmu(room_id, danmu)

    async def _process_danmu(self, room_id: str, danmu: dict[str, Any]) -> None:
        room = self._rooms.get(room_id)
        if room is None or not room.get("auto_reply", True):
            return
        if self._provider is None:
            return
        client = self._get_client()
        if client is None:
            return
        my_uid = _to_int(get_field(client, "my_uid", 0))
        if my_uid and _to_int(danmu.get("uid")) == my_uid:
            return
        text = str(danmu.get("text") or "")
        if not self._should_reply(room_id, danmu, text, my_uid):
            return
        if not self._reply_allowed(room_id):
            return
        if not await self.is_live(_to_int(room_id)):
            return
        result = await self._generate_reply(
            text, _to_int(room_id), str(danmu.get("name") or ""),
            _to_int(danmu.get("uid")),
        )
        replies = result.segments or ([result.text] if result.text else [])
        if not replies:
            return
        if self._screenshot_replies:
            await self._save_reply_frame(room_id)
        target_uid = _to_int(result.reply_to)
        target_name = ""
        if target_uid:
            for item in reversed(self.get_history(_to_int(room_id), _MAX_HISTORY)):
                if _to_int(item.get("uid")) == target_uid:
                    target_name = str(item.get("name") or "")
                    break
        for reply in replies:
            if not await self._post_danmaku(
                client, _to_int(room_id), reply,
                action="自动回复", reply_mid=target_uid, reply_uname=target_name,
            ):
                return
        self._record_reply(room_id)
        self._logger.info(
            f"B站直播已自动回复：房间 {room_id}，{len(replies)} 段，"
            f"共 {sum(len(item) for item in replies)} 字，"
            f"回复给 {target_uid or '无'}"
        )

    def _record_history(self, room_id: str, danmu: dict[str, Any]) -> None:
        text = str(danmu.get("text") or "").strip()
        if not text:
            return
        client = self._get_client()
        my_uid = _to_int(getattr(client, "my_uid", 0)) if client is not None else 0
        entry = {
            "uid": _to_int(danmu.get("uid")),
            "name": str(danmu.get("name") or ""),
            "text": text,
            "ts": time.time(),
            "time": datetime.now().astimezone().strftime("%H:%M:%S"),
            "at_me": bool(my_uid and _to_int(danmu.get("reply_mid")) == my_uid),
        }
        room_history = self._history.get(room_id)
        if room_history is None:
            room_history = self._history[room_id] = deque(maxlen=_MAX_HISTORY)
        room_history.append(entry)
        if self._summary_every:
            self._summary_counts[room_id] += 1
            if self._summary_counts[room_id] >= self._summary_every:
                self._summary_counts[room_id] = 0
                task = asyncio.create_task(self._summarize_live(room_id))
                self._summary_tasks.add(task)
                task.add_done_callback(self._summary_tasks.discard)

    async def _post_danmaku(
        self, client: Any, room_id: int, text: str, *,
        action: str, reply_mid: int = 0, reply_uname: str = "",
    ) -> bool:
        try:
            if reply_mid or reply_uname:
                sent = await call_client(
                    client.send_danmaku, room_id, text,
                    reply_mid=reply_mid, reply_uname=reply_uname,
                )
            else:
                sent = await call_client(client.send_danmaku, room_id, text)
        except Exception as exc:
            self._logger.warning(
                f"B站直播{action}发送失败：房间 {room_id}，"
                f"错误 {type(exc).__name__}: {exc}"
            )
            return False
        if not sent:
            self._logger.warning(f"B站直播{action}发送失败：房间 {room_id}，接口返回失败")
            return False
        self._record_history(
            str(room_id), {"uid": 0, "name": self._bot_name or "你", "text": text}
        )
        return True

    def _known_bot_names(self) -> tuple[str, ...]:
        """QQ 昵称 + B站账号昵称；后者用于识别 B站弹幕里的 @。"""
        names = [self._bot_name, *self._mention_names]
        service = self._service
        status = getattr(service, "status", None)
        if callable(status):
            try:
                uname = str((status() or {}).get("uname") or "").strip()
                if uname:
                    names.append(uname)
            except Exception:
                pass
        return tuple(name for name in names if name)

    def _should_reply(
        self, room_id: str, danmu: dict[str, Any], text: str, my_uid: int = 0
    ) -> bool:
        """直播间回复意愿：和 QQ 群聊同一套 manager/系数/@必回规则。"""
        if not str(text or "").strip():
            return False
        willing = self._willing_service
        if willing is None:
            return True
        try:
            history = self.get_history(_to_int(room_id), 20)
            observed = tuple(
                f"{item.get('name') or '观众'}: {item.get('text') or ''}"
                for item in history
                if str(item.get("text") or "").strip()
            )
            at_me = bool(
                my_uid and _to_int(danmu.get("reply_mid")) == my_uid
            )
            decision = willing.evaluate_live(
                room_id=_to_int(room_id),
                uid=_to_int(danmu.get("uid")),
                name=str(danmu.get("name") or ""),
                text=text,
                observed_messages=observed,
                extra_bot_names=self._known_bot_names(),
                base_probability=self._reply_chance,
                mentioned=at_me or None,
            )
        except Exception as exc:
            self._logger.warning(
                f"直播回复意愿计算失败，按不回复处理：房间 {room_id}，"
                f"错误 {type(exc).__name__}: {exc}"
            )
            return False
        self._logger.info(
            f"直播回复意愿：房间 {room_id}，概率 {decision.probability:.3f}，"
            f"判定{'回复' if decision.should_reply else '不回复'}，"
            f"依据：{'；'.join(decision.reasons)}"
        )
        return bool(decision.should_reply)

    def get_live_willingness(self, room_id: int = 0) -> dict[str, Any]:
        """查看直播间意愿系数（WillingService 的 live:<room> 会话系数）。"""
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        rid = _to_int(room_id)
        if rid > 0:
            return {
                "room_id": rid,
                "coefficient": self._willing_service.get_runtime_conversation_coefficient(
                    f"live:{rid}"
                ),
            }
        summary = self._willing_service.get_runtime_config_summary()
        return {"ok": True, "summary": summary}

    def set_live_willingness(self, room_id: int, value: float) -> dict[str, Any]:
        """设置直播间意愿系数 0.0~1.0（WillingService 的 live:<room> 会话系数）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        coefficient = max(0.0, min(1.0, float(value)))
        self._willing_service.set_runtime_conversation_coefficient(
            f"live:{rid}", coefficient
        )
        return {"ok": True, "room_id": rid, "coefficient": coefficient}

    def remove_live_willingness(self, room_id: int) -> dict[str, Any]:
        rid = _to_int(room_id)
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        self._willing_service.remove_runtime_conversation_coefficient(f"live:{rid}")
        return {"ok": True, "room_id": rid}

    def _mentions_bot(self, text: str) -> bool:
        lowered = text.lower()
        return any(name.lower() in lowered for name in self._known_bot_names())

    def _reply_allowed(self, room_id: str) -> bool:
        now = time.monotonic()
        last = self._last_reply_at.get(room_id)
        return last is None or now - last >= self._cooldown

    def _record_reply(self, room_id: str) -> None:
        self._last_reply_at[room_id] = time.monotonic()

    def _record_live_flow(self, room_id: int, system: str, messages: list[dict]) -> None:
        registry = self._flow_registry
        if registry is None:
            return
        try:
            key = f"bilibili_live:{room_id}"
            model = str(getattr(self._provider, "model", "") or "")
            registry.record_prompt(
                key,
                system_prompt=system,
                model=model,
                conversation_kind="bilibili_live",
                conversation_id=str(room_id),
            )
            registry.record_request(key, messages=messages, model=model, iteration=1)
        except Exception:
            pass

    async def _load_live_summaries(self) -> None:
        """启动时恢复直播间群档案；复用 QQ 的 group_summary/group_profile。"""
        if self._archive_service is None:
            return
        for room_id in list(self._rooms):
            key = _LIVE_ROOM_ARCHIVE_PREFIX + str(room_id)
            for table in ("group_summary", "group_profile"):
                try:
                    item = await self._archive_service.get(table, key)
                    value = str(getattr(item, "value", "") or "").strip()
                    if value:
                        self._room_memory[str(room_id)] = value
                        break
                except Exception as exc:
                    self._logger.debug(
                        "B站直播档案恢复失败", room_id=room_id, table=table, error=str(exc)
                    )

    async def _ensure_user_archive(self, uid: int, name: str) -> None:
        """每个 B 站观众在 user_profile 里都有对应档案；首次出现时建最小条目。"""
        if self._archive_service is None or uid <= 0 or uid in self._user_archive_seen:
            return
        self._user_archive_seen.add(uid)
        key = _LIVE_USER_ARCHIVE_PREFIX + str(uid)
        try:
            item = await self._archive_service.get("user_profile", key)
            if str(getattr(item, "value", "") or "").strip():
                return
            await self._archive_service.set(
                "user_profile",
                key,
                f"B站昵称：{name or '观众'}\nB站UID：{uid}",
                ["bilibili_live"],
            )
        except Exception as exc:
            self._logger.debug("B站直播观众档案初始化失败", uid=uid, error=str(exc))

    async def _load_user_memory(self, uid: int) -> str:
        """读取观众在 QQ 侧 user_summary/user_profile 的对应档案。"""
        if self._archive_service is None or uid <= 0:
            return ""
        if uid in self._user_memory:
            return self._user_memory[uid]
        key = _LIVE_USER_ARCHIVE_PREFIX + str(uid)
        value = ""
        for table in ("user_summary", "user_profile"):
            try:
                item = await self._archive_service.get(table, key)
                text = str(getattr(item, "value", "") or "").strip()
                if text:
                    value = text
                    break
            except Exception as exc:
                self._logger.debug(
                    "B站直播观众档案读取失败", uid=uid, table=table, error=str(exc)
                )
        self._user_memory[uid] = value
        return value

    async def _summarize_live(self, room_id: str) -> None:
        """每 N 条弹幕总结一次；只保留话题/梗/人和事件，不逐条复述。"""
        try:
            lines = self.format_history(_to_int(room_id), self._summary_every)
            if not lines:
                return
            summary = await self._chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是直播弹幕总结器。把弹幕浓缩成一段直播记忆，"
                            "只保留话题、梗、反复出现的人/事件和约定；不要逐条复述，200 字以内。"
                        ),
                    },
                    {"role": "user", "content": lines},
                ],
                error_label="B站直播弹幕总结失败",
            )
            summary = summary.strip()
            if not summary:
                return
            self._room_memory[room_id] = summary[:2000]
            if self._archive_service is not None:
                try:
                    await self._archive_service.set(
                        "group_summary",
                        _LIVE_ROOM_ARCHIVE_PREFIX + str(room_id),
                        summary[:2000],
                        ["bilibili_live"],
                    )
                except Exception as exc:
                    self._logger.debug("B站直播总结写档案失败", error=str(exc))
            self._logger.info(f"B站直播弹幕已总结：房间 {room_id}，摘要 {len(summary)} 字")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "B站直播弹幕总结失败", room_id=room_id, error=f"{type(exc).__name__}: {exc}"
            )

    async def _live_asr_context(self, room_id: int) -> str:
        """按房间 ASR 开关截取最近 10 秒直播语音；失败只记日志。"""
        if self._asr_service is None:
            return ""
        room = self._rooms.get(str(_to_int(room_id))) or {}
        if not bool(room.get("asr", self._asr_default_enabled)):
            return ""
        try:
            result = await self.transcribe(_to_int(room_id), seconds=10)
        except Exception as exc:
            self._logger.debug("直播 ASR 上下文读取失败", room_id=room_id, error=str(exc))
            return ""
        if not result.get("ok"):
            return ""
        text = str(result.get("text") or "").strip()
        return text[:1200]

    def _live_persona(self) -> str:
        """读取 custom/prompts.toml 的 [live_chat]；为空则回退 QQ 风格默认提示词。"""
        if self._prompt_store is None:
            return ""
        try:
            from neobot_app.prompt.store import get_template_value

            return str(get_template_value(self._prompt_store, "live_chat") or "").strip()
        except Exception:
            return ""

    async def _generate_observation(self, room_id: int) -> Any:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            text="",
            recent_history=self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            frame_context=await self.frame_context(room_id),
        )
        system, content = build_live_observation_prompt(ctx, self._live_persona())
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            return await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
                allow_reply_to=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "B站直播主动观察生成失败",
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

    async def _save_reply_frame(self, room_id: int) -> None:
        if self._media is None:
            return
        try:
            result = await call_client(self._media.capture_frame, _to_int(room_id))
            if isinstance(result, dict) and result.get("ok"):
                self._logger.info(
                    "B站直播回复截图已保留",
                    room_id=room_id,
                    path=result.get("path"),
                )
        except Exception as exc:
            self._logger.debug("B站直播回复截图失败", room_id=room_id, error=str(exc))

    async def _auto_look_loop(self) -> None:
        while self._running:
            await asyncio.sleep(30)
            if not self._auto_look_enabled:
                continue
            now = time.monotonic()
            if now - self._last_auto_look < self._auto_look_interval_minutes * 60:
                continue
            self._last_auto_look = now
            for room_id, room in list(self._rooms.items()):
                if not room.get("auto_reply", True):
                    continue
                if not await self.is_live(_to_int(room_id)):
                    continue
                try:
                    result = await self._generate_observation(_to_int(room_id))
                    segments = (
                        result.segments or ([result.text] if result.text else [])
                    ) if result is not None else []
                    if not segments:
                        continue
                    client = self._get_client()
                    if client is None:
                        continue
                    for text in segments:
                        await self._post_danmaku(
                            client, _to_int(room_id), text, action="主动观察"
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._logger.warning(
                        "B站直播主动观察失败",
                        room_id=room_id,
                        error=f"{type(exc).__name__}: {exc}",
                    )

    async def _generate_reply(
        self, text: str, room_id: int, user_name: str = "", user_id: int = 0
    ) -> Any:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            viewer_name=user_name,
            text=text,
            recent_history=self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            viewer_memory=await self._load_user_memory(user_id),
            frame_context="",
        )
        system, content = build_live_danmaku_prompt(ctx, self._live_persona())
        asr_context = await self._live_asr_context(room_id)
        if asr_context:
            content += f"\n<直播语音>{asr_context}</直播语音>"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            result = await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
                allow_reply_to=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "B站直播回复生成失败",
                error=f"{type(exc).__name__}: {exc}",
            )
            return ToolReply()
        return result

    async def _generate_schedule_danmaku(
        self, prompt: str, context: str, room_id: int
    ) -> list[str]:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            text=prompt,
            recent_history=context or self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            frame_context="",
            scheduled_prompt=prompt,
        )
        system, content = build_live_scheduled_prompt(ctx, self._live_persona())
        asr_context = await self._live_asr_context(room_id)
        if asr_context:
            content += f"\n<直播语音>{asr_context}</直播语音>"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            result = await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "B站直播定时弹幕生成失败",
                error=f"{type(exc).__name__}: {exc}",
            )
            return []
        return result.segments or ([result.text] if result.text else [])

    async def _chat(self, messages: list[dict[str, str]], *, error_label: str) -> str:
        if self._provider is None:
            return ""
        try:
            response = self._provider.chat(messages)
            if inspect.isawaitable(response):
                response = await response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"{error_label}：{type(exc).__name__}: {exc}")
            return ""
        content = response.get("content", "") if isinstance(response, dict) else get_field(response, "content", "")
        return str(content or "")

    # ── 定时弹幕循环 ──

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
        if str(schedule.get("time") or "") != now.strftime("%H:%M"):
            return False
        last = str(schedule.get("last_fired_date") or "")
        recurrence = str(schedule.get("recurrence") or "")
        if recurrence == "once":
            return not last
        if recurrence == "daily":
            return last != now.date().isoformat()
        if recurrence == "weekly":
            try:
                last_date = date.fromisoformat(last)
            except ValueError:
                return True
            return (now.date() - last_date).days >= 7
        return False

    async def _scan_schedules(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """检查到点的定时弹幕；到点即消耗本时段，下播/失败都不在同一时段重试。"""
        current = now or datetime.now().astimezone()
        fired: list[dict[str, Any]] = []
        for room_id, room in list(self._rooms.items()):
            for schedule in list(room.get("schedules") or []):
                if not self._is_schedule_due(schedule, current):
                    continue
                schedule["last_fired_date"] = current.date().isoformat()
                self._save()
                rid = _to_int(room_id)
                if not await self.is_live(rid):
                    self._logger.info(
                        "B站直播间未开播，跳过定时弹幕",
                        room_id=room_id,
                        schedule_id=schedule.get("id"),
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
                fired.append(
                    {
                        "room_id": rid,
                        "schedule_id": schedule.get("id"),
                        "text": text,
                    }
                )
                self._logger.info(
                    "B站直播已发送定时弹幕",
                    room_id=room_id,
                    schedule_id=schedule.get("id"),
                    chars=len(text),
                )
        return fired

    def _format_history(self, room_id: int, count: int = 50) -> str:
        return self.format_history(room_id, count)

    def _get_client(self) -> Any | None:
        """取当前可用 client；BilibiliService 休眠时 resolve_client 会回退成 service 本身。"""
        client = resolve_client(self._service)
        return client if callable(getattr(client, "send_danmaku", None)) else None

    def _start_task(self, room_id: str) -> None:
        if not self._running:
            return
        task = self._tasks.get(room_id)
        if task is not None and not task.done():
            return
        self._tasks[room_id] = asyncio.create_task(self._room_loop(room_id), name=f"bilibili-live-{room_id}")

    async def _cancel_task(self, room_id: str) -> None:
        task = self._tasks.pop(room_id, None)
        if task is None:
            return
        task.cancel()
        if task is not asyncio.current_task():
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
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
            self._logger.warning("B站直播交互状态保存失败", error=str(exc))


def _client_user_agent(client: Any) -> str:
    """取 client 实际发 HTTP 的 UA，保证 getDanmuInfo 与 WS token 绑定一致。"""
    ua = str(get_field(client, "user_agent", "") or "")
    if not ua:
        session = get_field(client, "_session", None)
        headers = getattr(session, "headers", None)
        if headers is not None:
            ua = str(headers.get("User-Agent") or "")
    return ua or DEFAULT_USER_AGENT


def _normalize_clock(value: Any) -> str | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour:02d}:{minute:02d}"


def _normalize_schedule(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    clock = _normalize_clock(value.get("time"))
    recurrence = str(value.get("recurrence") or "").strip().lower()
    prompt = str(value.get("prompt") or "").strip()
    if clock is None or recurrence not in _RECURRENCES or not prompt:
        return None
    return {
        "id": str(value.get("id") or uuid4().hex[:12]),
        "time": clock,
        "recurrence": recurrence,
        "prompt": prompt,
        "last_fired_date": str(value.get("last_fired_date") or ""),
    }


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
