"""开播/下播轮询。

设计要点：
- 只轮询「至少被一个群订阅」的房间（跨群去重），不轮询没人要的房间；
- 用 get_info 一次拿全直播状态 + 标题 + 封面 + 分区 + 人气，卡片需要的数据都在里面；
- 状态变化落库（room_states），首次见到某房间只记录不通知，避免重启后误报；
- 单个房间失败不影响其他房间，整个循环不抛异常。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import db
from .bilibili.client import BilibiliLiveClient
from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .bilibili.models import LiveRoomInfo
from .logs import log_at

EVENT_LIVE = "live"
EVENT_LIVE_END = "live_end"


@dataclass(frozen=True)
class RoomSnapshot:
    """一次观测到的直播间状态。"""

    room_id: int
    live_status: int
    title: str = ""
    cover_url: str = ""
    area_name: str = ""
    online: int = 0
    live_time: datetime | None = None

    @property
    def is_living(self) -> bool:
        """B 站 live_status：0 未开播 / 1 直播中 / 2 轮播。只把 1 视为开播。"""
        return self.live_status == 1

    @classmethod
    def from_room_info(cls, info: LiveRoomInfo) -> RoomSnapshot:
        return cls(
            room_id=info.room_id,
            live_status=info.live_status,
            title=info.title,
            cover_url=info.cover,
            area_name=info.area_name,
            online=info.online,
            live_time=info.live_time,
        )


@dataclass(frozen=True)
class Transition:
    """状态跳变，通知层要处理的就是它。"""

    kind: str
    room_id: int
    snapshot: RoomSnapshot
    previous_status: int


def detect_transition(
    previous_status: int | None, snapshot: RoomSnapshot
) -> str | None:
    """判断状态跳变；首次见到某房间（previous_status 为 None）只记录不通知。

    这样插件重启后不会把「已经在播」的房间误报成刚开播。
    """
    if previous_status is None:
        return None
    was_living = previous_status == 1
    if snapshot.is_living and not was_living:
        return EVENT_LIVE
    if was_living and not snapshot.is_living:
        return EVENT_LIVE_END
    return None


@dataclass
class PollStats:
    checked: int = 0
    failed: int = 0
    transitions: int = 0
    errors: list[str] = field(default_factory=list)


class LivePoller:
    """按固定间隔检查所有被订阅的直播间。"""

    def __init__(
        self,
        *,
        client: BilibiliLiveClient,
        database: Any,
        poll_interval: float = 60.0,
        concurrency: int = 4,
        logger: Any = None,
    ) -> None:
        self._client = client
        self._database = database
        self._interval = max(15.0, float(poll_interval))
        self._concurrency = max(1, int(concurrency))
        self._logger = logger
        self._wake = asyncio.Event()
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_stats = PollStats()
        self.last_error = ""

    def request_check(self) -> None:
        """新增订阅后唤醒主循环，仍由唯一轮询任务完成落库和跳变判断。"""
        self._wake.set()

    def _record_stats(self, stats: PollStats) -> None:
        self.last_finished_at = datetime.now(UTC)
        self.last_stats = stats
        self.last_error = "；".join(stats.errors)
        if stats.checked:
            self.last_success_at = self.last_finished_at

    async def _fetch(
        self, room_id: int, semaphore: asyncio.Semaphore
    ) -> RoomSnapshot | None:
        async with semaphore:
            try:
                info = await self._client.fetch_live_room_info(room_id)
            except (BilibiliAPIError, BilibiliTransportError) as exc:
                log_at(self._logger, "warning", f"轮询直播间 {room_id} 失败: {exc}")
                return None
            except Exception as exc:
                log_at(self._logger, "warning", f"轮询直播间 {room_id} 异常: {exc!r}")
                return None
        return RoomSnapshot.from_room_info(info)

    async def poll_once(self) -> tuple[list[Transition], PollStats]:
        """检查一轮；返回本轮的状态跳变。"""
        self.last_started_at = datetime.now(UTC)
        stats = PollStats()
        transitions: list[Transition] = []
        async with self._database.session() as session:
            room_ids = await db.distinct_room_ids(session)
        if not room_ids:
            self._record_stats(stats)
            return transitions, stats

        semaphore = asyncio.Semaphore(self._concurrency)
        snapshots = await asyncio.gather(
            *(self._fetch(room_id, semaphore) for room_id in room_ids)
        )

        async with self._database.transaction() as session:
            for room_id, snapshot in zip(room_ids, snapshots, strict=True):
                if snapshot is None:
                    stats.failed += 1
                    stats.errors.append(
                        f"直播间 {room_id} 检查失败，请检查平台连接后重试。"
                    )
                    continue
                stats.checked += 1
                previous = await db.get_room_state(session, room_id)
                previous_status = (
                    int(previous.live_status) if previous is not None else None
                )
                kind = detect_transition(previous_status, snapshot)
                row = await db.upsert_room_state(
                    session,
                    room_id,
                    live_status=snapshot.live_status,
                    title=snapshot.title,
                    cover_url=snapshot.cover_url,
                    area_name=snapshot.area_name,
                    online=snapshot.online,
                    live_time=snapshot.live_time,
                )
                if kind == EVENT_LIVE:
                    row.last_seen_live_at = datetime.now(UTC)
                elif kind == EVENT_LIVE_END:
                    row.last_ended_at = datetime.now(UTC)
                if kind is not None:
                    transitions.append(
                        Transition(
                            kind=kind,
                            room_id=room_id,
                            snapshot=snapshot,
                            previous_status=previous_status,
                        )
                    )
                    stats.transitions += 1
        self._record_stats(stats)
        return transitions, stats

    async def refresh(self, room_ids: list[int]) -> dict[int, RoomSnapshot]:
        """按需查询一组房间的当前状态：不写库、不发通知，仅用于即时展示。

        /开播状态 用它保证总览图是实时的，而不是等下一次轮询；
        写库与跳变判定仍然只由 poll_once 负责，避免这里悄悄吞掉一次真实的开播跳变。
        """
        if not room_ids:
            return {}
        semaphore = asyncio.Semaphore(self._concurrency)
        snapshots = await asyncio.gather(
            *(self._fetch(room_id, semaphore) for room_id in room_ids)
        )
        return {
            room_id: snapshot
            for room_id, snapshot in zip(room_ids, snapshots, strict=True)
            if snapshot is not None
        }

    async def run(
        self,
        stop: asyncio.Event,
        on_transition: Callable[[Transition], Awaitable[None]],
    ) -> None:
        """轮询主循环，直到 stop 被设置。"""
        while not stop.is_set():
            self._wake.clear()
            try:
                transitions, stats = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_at(self._logger, "warning", f"轮询周期异常: {exc!r}")
                transitions, stats = (
                    [],
                    PollStats(errors=["轮询未完成，请检查插件数据与平台连接。"]),
                )
                self._record_stats(stats)
            if stats.checked or stats.failed:
                log_at(
                    self._logger,
                    "debug",
                    f"轮询完成: 成功 {stats.checked} 失败 {stats.failed} 跳变 {stats.transitions}",
                )
            for transition in transitions:
                try:
                    await on_transition(transition)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_at(
                        self._logger,
                        "warning",
                        f"处理跳变失败 ({transition.kind} {transition.room_id}): {exc!r}",
                    )
            await self._wait_next(stop)

    async def _wait_next(self, stop: asyncio.Event) -> None:
        """关停和新增订阅都能结束等待，取消时收回两个短期等待任务。"""
        waiters = (
            asyncio.create_task(stop.wait()),
            asyncio.create_task(self._wake.wait()),
        )
        try:
            await asyncio.wait(
                waiters, timeout=self._interval, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in waiters:
                task.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
