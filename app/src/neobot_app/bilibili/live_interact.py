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

实现在 neobot_app.bilibili.live_parts（常量、小工具与六组 mixin），
本模块只保留类定义、生命周期与心跳。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp  # noqa: F401 - 单测按 live_interact.aiohttp 打桩（打的是模块对象本身）

from neobot_app.bilibili._compat import RecentIds
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.bilibili.live_parts.constants import (
    _ARCHIVE_CONCURRENCY,
    _DANMU_MAX_PENDING,
    _MAX_EVENT_KEYS,
    _WS_AUTH_MAX_FAILURES,
    _WS_HEARTBEAT_SECONDS,
    _WS_OP_HEARTBEAT,
    _WS_RECEIVE_TIMEOUT_SECONDS,
)
from neobot_app.bilibili.live_parts.generation import _GenerationMixin
from neobot_app.bilibili.live_parts.media import _MediaMixin
from neobot_app.bilibili.live_parts.reply import _ReplyMixin
from neobot_app.bilibili.live_parts.rooms import _RoomsMixin
from neobot_app.bilibili.live_parts.schedules import _SchedulesMixin
from neobot_app.bilibili.live_parts.ws import _WebSocketMixin
from neobot_app.bilibili.live_protocol import (
    LiveEvent,
    decode_packets,
    encode_packet,
    parse_danmu_message,
)
from neobot_app.bilibili.prompts import MAX_LIVE_DANMAKU_CHARS
from neobot_app.core import DATA_DIR
from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.logging import Logger

__all__ = (
    "BilibiliLiveInteractor",
    "DEFAULT_USER_AGENT",
    "decode_packets",
    "encode_packet",
    "parse_danmu_message",
    # 拆分后这些私有常量仍按模块名对外，单测/调用方按名字取用。
    "_DANMU_MAX_PENDING",
    "_WS_AUTH_MAX_FAILURES",
    "_WS_RECEIVE_TIMEOUT_SECONDS",
)

_LOGGER = get_module_logger("bilibili.live_interact")


class BilibiliLiveInteractor(
    _RoomsMixin,
    _MediaMixin,
    _WebSocketMixin,
    _ReplyMixin,
    _GenerationMixin,
    _SchedulesMixin,
):
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
        # 保留参数兼容 runtime 传参；是否只回 @ 已由意愿服务（evaluate_live）统一判定。
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
        self._archive_semaphore = asyncio.Semaphore(_ARCHIVE_CONCURRENCY)
        self._summary_tasks: set[asyncio.Task[None]] = set()
        self._last_auto_look = time.monotonic()
        self._live_cache: dict[str, tuple[float, bool]] = {}
        self._schedule_task: asyncio.Task[None] | None = None
        self._auto_look_task: asyncio.Task[None] | None = None
        self._reply_locks: dict[str, asyncio.Lock] = {}
        self._reply_tasks: set[asyncio.Task[None]] = set()
        #: 自己的 B站 UID 缓存：client.my_uid 是属性，未缓存时会打 nav 接口，不能在事件循环里读。
        self._my_uid = 0
        #: 每房间正在排队的弹幕数（_DANMU_MAX_PENDING 上限）。
        self._pending_danmu: dict[str, int] = {}
        #: 发送失败后的冷却截止时刻（monotonic）。
        self._send_fail_until: dict[str, float] = {}
        #: 状态文件解析失败且备份也失败时置 True，_save() 不再覆盖原文件。
        self._state_broken = False
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
        """没在跑就启动；已在跑时补上缺失/已退出的房间任务（登录、命令开启前调用，幂等）。"""
        if not self._running:
            await self.start()
            return
        for room_id in list(self._rooms):
            self._start_task(room_id)

    async def stop(self) -> None:
        """停止所有监听任务（含弹幕/事件/档案/总结后台任务）；持久化状态保留，下次 start() 恢复。"""
        self._running = False
        room_tasks = list(self._tasks.values())
        self._tasks.clear()
        single_tasks = [task for task in (self._schedule_task, self._auto_look_task) if task is not None]
        self._schedule_task = None
        self._auto_look_task = None
        groups = (self._event_tasks, self._reply_tasks, self._summary_tasks, self._user_memory_tasks)
        extra_tasks = [task for group in groups for task in group]
        for group in groups:
            group.clear()
        self._pending_danmu.clear()
        await self._cancel_tasks(room_tasks + single_tasks + extra_tasks)
        self._logger.info("B站直播交互器已停止")

    @staticmethod
    async def _cancel_tasks(tasks: list[asyncio.Task[Any]]) -> None:
        """快照-取消-await 一批任务；只吞 CancelledError，其它异常交给任务自身日志。"""
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @property
    def is_running(self) -> bool:
        return self._running

    # 心跳留在门面：单测 monkeypatch live_interact._WS_HEARTBEAT_SECONDS 从这里读。
    async def _heartbeat(self, ws: Any) -> None:
        """定时发心跳；发送失败说明连接已坏，主动关闭并抛出，让 _room_loop 重连。"""
        while True:
            await asyncio.sleep(_WS_HEARTBEAT_SECONDS)
            try:
                await ws.send_bytes(encode_packet(_WS_OP_HEARTBEAT))
            except Exception as exc:
                self._logger.warning(f"B站直播心跳发送失败，主动断开重连：{type(exc).__name__}: {exc}")
                with contextlib.suppress(Exception):
                    await ws.close()
                raise
