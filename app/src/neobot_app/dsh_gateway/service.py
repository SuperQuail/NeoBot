"""网关核心服务：报告去重、命令 ack/重发、长轮询唤醒与健康快照。

并发约定：

- 所有状态只在事件循环内读写，不需要线程锁；
- 同一个 daemon 的 ``sync`` / ``wait_for_commands`` 通过 per-daemon
  :class:`asyncio.Lock` 串行，插件 handler 不会被同一 daemon 的并发回调打乱；
- ``notify()`` 是同步方法（只 set :class:`asyncio.Event`），插件可在任意协程里
  先入队命令、再调用它唤醒长轮询。

命令语义（v1）：

- ``drain_commands`` 取出的命令先进入该 daemon 的 pending 表再下发；
- daemon 下一次请求的 ``acks`` 到达后才会从 pending 删除；
- 未 ack 的命令每轮重发（按首次下发顺序），因此 daemon 崩溃/断线不会丢命令；
- pending 有上限（``MAX_PENDING_COMMANDS``），超过时丢弃最旧的一条并告警——
  宁可让插件重做，也不让内存无界增长。

本服务不持有任何业务状态：报告交给插件 handler，命令由插件 handler 给出。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from neobot_contracts.ports.logging import Logger, NullLogger

from .models import DaemonCommand, SyncReport, SyncRequest, SyncResponse

#: 单个 daemon 最多同时挂起多少条未 ack 命令；超过时丢弃最旧的一条。
MAX_PENDING_COMMANDS = 256


@dataclass(slots=True)
class _DaemonState:
    """单个 daemon 的运行时状态（全部在事件循环内读写）。"""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    last_seq: int = 0
    #: 是否处理过至少一个 seq；用于让首个 ``seq=0`` 不被当成重复。
    has_seq: bool = False
    last_seen: float | None = None
    #: daemon 自报的 health 快照（原样留存，只做观察）。
    health: dict[str, Any] = field(default_factory=dict)
    #: 已下发未 ack 的命令：command_id -> (命令, 最近一次下发时间)。
    #: dict 的插入顺序即「首次下发顺序」，重发时保持该顺序。
    pending: dict[str, tuple[DaemonCommand, float]] = field(default_factory=dict)
    #: 正在处理/挂起的同步请求数；>0 时健康快照里 connected=True。
    inflight: int = 0


class DaemonHandler(Protocol):
    """插件实现的处理协议；由 ``DshGatewayService.register_handler`` 注册。"""

    async def on_reports(self, daemon_id: str, reports: list[SyncReport]) -> None:
        """处理一批新报告（按 seq 去重后只会收到新报告）。"""

    async def drain_commands(self, daemon_id: str) -> list[DaemonCommand]:
        """取走该 daemon 待下发的命令（已取走的命令不应再返回）。"""


class DshGatewayService:
    """daemon 同步的宿主服务，注册进宿主服务表供插件读取。"""

    def __init__(self, *, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._handlers: dict[str, DaemonHandler] = {}
        self._states: dict[str, _DaemonState] = {}

    # ── handler 注册 ────────────────────────────────────────────

    def register_handler(self, plugin_name: str, handler: DaemonHandler) -> None:
        """注册插件 handler；同名重复注册以最后一次为准（便于热重载）。"""
        name = str(plugin_name or "").strip()
        if not name:
            raise ValueError("plugin_name is required")
        if not callable(getattr(handler, "on_reports", None)) or not callable(getattr(handler, "drain_commands", None)):
            raise TypeError("handler 必须实现 on_reports / drain_commands")
        self._handlers[name] = handler
        self._logger.info(
            "DSH 网关插件 handler 已注册",
            event="dsh_gateway.handler_registered",
            plugin_name=name,
        )

    def unregister_handler(self, plugin_name: str) -> bool:
        """注销插件 handler；返回此前是否存在。"""
        name = str(plugin_name or "").strip()
        if not name:
            return False
        removed = self._handlers.pop(name, None) is not None
        if removed:
            self._logger.info(
                "DSH 网关插件 handler 已注销",
                event="dsh_gateway.handler_unregistered",
                plugin_name=name,
            )
        return removed

    @property
    def handler_plugins(self) -> tuple[str, ...]:
        """当前已注册 handler 的插件名（只读，便于诊断）。"""
        return tuple(self._handlers)

    def _active_handler(self) -> DaemonHandler | None:
        # 后注册者优先：热重载时新 handler 覆盖旧对象，旧对象随 unregister 退出。
        if not self._handlers:
            return None
        return next(reversed(self._handlers.values()))

    # ── 同步 ────────────────────────────────────────────────────

    async def sync(self, request: SyncRequest) -> SyncResponse:
        """处理一次同步：先确认已下发命令，再按 seq 投递报告，最后取全部未 ack 命令。"""
        state = self._state(request.daemon_id)
        state.health = dict(request.health)
        state.last_seen = time.time()
        state.inflight += 1
        try:
            async with state.lock:
                self._consume_acks(state, request.acks)
                # 首个请求（即使 seq=0）也要投递；之后只有在 seq 前进时才投递。
                if not state.has_seq or request.seq > state.last_seq:
                    await self._deliver(request)
                    state.last_seq = request.seq
                    state.has_seq = True
                elif request.reports:
                    self._logger.debug(
                        "忽略重发的报告（seq 已处理）",
                        event="dsh_gateway.duplicate_seq",
                        daemon_id=request.daemon_id,
                        seq=request.seq,
                        last_seq=state.last_seq,
                    )
                commands = await self._collect_commands(request.daemon_id, state)
                return SyncResponse(
                    daemon_id=request.daemon_id,
                    cursor=state.last_seq,
                    commands=commands,
                )
        finally:
            state.inflight -= 1
            state.last_seen = time.time()

    def _consume_acks(self, state: _DaemonState, acks: list[str]) -> None:
        """按 daemon 的 ack 删除 pending；未知 id / 重复 ack 一律无害忽略。"""
        for command_id in acks:
            state.pending.pop(command_id, None)

    async def _deliver(self, request: SyncRequest) -> None:
        """把新报告交给 handler；handler 失败时不推进游标，daemon 会重发。"""
        handler = self._active_handler()
        if handler is None or not request.reports:
            return
        await handler.on_reports(request.daemon_id, list(request.reports))

    async def _drain(self, daemon_id: str) -> list[DaemonCommand]:
        """调用 handler 取命令；调用方负责持有该 daemon 的锁。"""
        handler = self._active_handler()
        if handler is None:
            return []
        return list(await handler.drain_commands(daemon_id) or ())

    async def _collect_commands(self, daemon_id: str, state: _DaemonState) -> list[DaemonCommand]:
        """drain 新命令并入 pending，返回全部未 ack 命令（含本轮新命令）。

        调用方持有该 daemon 的锁。返回前刷新 pending 的 ``sent_at``；同一 command
        id 只保留首次入队的那一份，重发时顺序与首次下发一致。
        """
        untracked: list[DaemonCommand] = []
        for command in await self._drain(daemon_id):
            command_id = str(getattr(command, "id", "") or "").strip()
            if not command_id:
                # 插件下发的命令没有 id 就无法被 daemon ack；本轮照常下发，但不入表。
                self._logger.warning(
                    "插件下发的命令缺少 id，无法跟踪 ack",
                    event="dsh_gateway.command_without_id",
                    daemon_id=daemon_id,
                    kind=getattr(command, "kind", ""),
                )
                untracked.append(command)
                continue
            if command_id not in state.pending:
                state.pending[command_id] = (command, time.time())
        self._trim_pending(state)
        now = time.time()
        commands: list[DaemonCommand] = []
        for command_id, (command, _sent_at) in state.pending.items():
            state.pending[command_id] = (command, now)
            commands.append(command)
        return commands + untracked

    def _trim_pending(self, state: _DaemonState) -> None:
        """pending 超过上限时丢弃最旧的命令，避免插件故障导致内存无界增长。"""
        while len(state.pending) > MAX_PENDING_COMMANDS:
            dropped_id = next(iter(state.pending))
            state.pending.pop(dropped_id, None)
            self._logger.warning(
                "未 ack 命令超过上限，已丢弃最旧的一条",
                event="dsh_gateway.pending_overflow",
                command_id=dropped_id,
                limit=MAX_PENDING_COMMANDS,
            )

    # ── 长轮询 ──────────────────────────────────────────────────

    async def wait_for_commands(self, daemon_id: str, timeout_seconds: float) -> list[DaemonCommand]:
        """等待新命令（最多 ``timeout_seconds`` 秒）；返回全部未 ack 命令。

        先 clear 再 drain：即使 ``notify`` 恰好发生在两次 drain 之间，命令也已经
        入队、会被随后的 drain 取到，不会丢。已有 pending 时立即返回，不挂起。
        """
        state = self._state(daemon_id)
        state.last_seen = time.time()
        state.inflight += 1
        event = state.wakeup
        try:
            event.clear()
            async with state.lock:
                commands = await self._collect_commands(daemon_id, state)
            if commands:
                return commands
            if timeout_seconds > 0:
                try:
                    await asyncio.wait_for(event.wait(), timeout_seconds)
                except TimeoutError:
                    pass
            event.clear()
            async with state.lock:
                return await self._collect_commands(daemon_id, state)
        finally:
            state.inflight -= 1
            state.last_seen = time.time()

    def notify(self, daemon_id: str) -> None:
        """唤醒该 daemon 正在挂起的长轮询；未知 daemon 忽略（下次 sync 会自建状态）。"""
        state = self._states.get(str(daemon_id or "").strip())
        if state is not None:
            state.wakeup.set()

    # ── 健康与状态 ──────────────────────────────────────────────

    def health_snapshot(self) -> list[dict[str, Any]]:
        """每个见过面的 daemon 一行：daemon_id / last_seq / last_seen / connected。"""
        return [
            {
                "daemon_id": daemon_id,
                "last_seq": state.last_seq,
                "last_seen": state.last_seen,
                "connected": state.inflight > 0,
            }
            for daemon_id, state in sorted(self._states.items())
        ]

    def last_health(self, daemon_id: str) -> dict[str, Any]:
        """daemon 最近一次上报的 health 字段（只做观察，不做判定）。"""
        state = self._states.get(str(daemon_id or "").strip())
        return dict(state.health) if state is not None else {}

    def clear(self) -> None:
        """清空 daemon 状态（测试/收尾用）；handler 注册不受影响。"""
        self._states.clear()

    def _state(self, daemon_id: str) -> _DaemonState:
        key = str(daemon_id or "").strip()
        if not key:
            raise ValueError("daemon_id is required")
        state = self._states.get(key)
        if state is None:
            state = _DaemonState()
            self._states[key] = state
        return state


__all__ = ["DaemonHandler", "DshGatewayService"]
