"""BrowserLifecycleManager — 浏览器生命周期管理（per-chat-flow）。

每个聊天流独立跟踪浏览器使用状态：
- 10 分钟无访问 → 自动关闭该流的页面（除非被 hold）
- hold 最长 2 小时
- 后台定时任务检查闲置流并关闭

使用稳定的 tab_id（而非会变化的 index）跟踪标签页。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class _FlowState:
    """单个聊天流的浏览器状态。"""

    last_access: float = field(default_factory=time.time)
    held_until: float | None = None
    tab_ids: set[str] = field(default_factory=set)


class BrowserLifecycleManager:
    """Per-chat-flow 浏览器生命周期管理器。

    每个 pipeline_key 独立跟踪：
    - last_access: 最近一次浏览器工具调用时间
    - held_until: hold 过期时间（如果有）
    - tab_ids: 该流分配的浏览器标签页稳定 ID 集合
    """

    def __init__(
        self,
        idle_timeout_minutes: int = 10,
        hold_max_minutes: int = 120,
    ) -> None:
        self._idle_timeout = idle_timeout_minutes * 60
        self._hold_max = hold_max_minutes * 60
        self._flows: dict[str, _FlowState] = {}
        self._lock = asyncio.Lock()
        self._bg_task: asyncio.Task | None = None
        self._on_close_flow: Callable[[str, set[str]], Any] | None = None
        self._browser_instance: Any = None

    # ── 回调设置 ──

    def set_close_callback(self, cb: Callable[[str, set[str]], Any]) -> None:
        """设置关闭流时的回调。

        cb(chat_flow_id, tab_ids) — 关闭该流的所有标签页。
        tab_ids 是稳定的标签页 ID 集合。
        """
        self._on_close_flow = cb

    def set_browser_instance(self, browser: Any) -> None:
        """关联浏览器实例。"""
        self._browser_instance = browser

    # ── 流状态查询 ──

    def get_tab_ids(self, chat_flow_id: str) -> set[str]:
        """获取该聊天流分配的标签页 ID 集合。"""
        state = self._flows.get(chat_flow_id)
        return set(state.tab_ids) if state else set()

    def is_held(self, chat_flow_id: str) -> bool:
        """该聊天流是否在 hold 中。"""
        state = self._flows.get(chat_flow_id)
        if state is None or state.held_until is None:
            return False
        if time.time() >= state.held_until:
            state.held_until = None
            return False
        return True

    @property
    def active_flow_count(self) -> int:
        """活跃的聊天流数量（有标签页的）。"""
        return sum(1 for s in self._flows.values() if s.tab_ids)

    # ── 操作 ──

    def touch(self, chat_flow_id: str) -> None:
        """更新聊天流的最后访问时间。"""
        if chat_flow_id not in self._flows:
            self._flows[chat_flow_id] = _FlowState()
        else:
            self._flows[chat_flow_id].last_access = time.time()

    def track_tab_open(self, chat_flow_id: str, tab_id: str) -> None:
        """记录聊天流打开了一个标签页。"""
        self.touch(chat_flow_id)
        self._flows[chat_flow_id].tab_ids.add(tab_id)

    def track_tab_close(self, chat_flow_id: str, tab_id: str) -> None:
        """记录聊天流关闭了一个标签页。"""
        state = self._flows.get(chat_flow_id)
        if state:
            state.tab_ids.discard(tab_id)

    def hold(self, chat_flow_id: str, minutes: int | None = None) -> bool:
        """Hold 一个聊天流的页面，防止被自动关闭。

        Args:
            chat_flow_id: 聊天流 ID
            minutes: hold 分钟数，默认使用最大值（2 小时）

        Returns:
            True 表示成功 hold
        """
        duration_seconds = min(
            (minutes or self._hold_max // 60) * 60,
            self._hold_max,
        )
        if chat_flow_id not in self._flows:
            self._flows[chat_flow_id] = _FlowState()
        self._flows[chat_flow_id].held_until = time.time() + duration_seconds
        self._flows[chat_flow_id].last_access = time.time()
        return True

    def release(self, chat_flow_id: str) -> bool:
        """释放聊天流的 hold 状态。"""
        state = self._flows.get(chat_flow_id)
        if state and state.held_until is not None:
            state.held_until = None
            return True
        return False

    def reset_flow(self, chat_flow_id: str) -> None:
        """重置聊天流状态（关闭页面后调用）。"""
        self._flows.pop(chat_flow_id, None)

    # ── 闲置检测 ──

    def _get_idle_flows(self) -> list[tuple[str, set[str]]]:
        """获取闲置且未被 hold 的聊天流及其标签页 ID。

        Returns:
            [(chat_flow_id, tab_ids), ...]
        """
        now = time.time()
        idle: list[tuple[str, set[str]]] = []
        for cid, state in list(self._flows.items()):
            if not state.tab_ids:
                continue
            if state.held_until is not None and now >= state.held_until:
                state.held_until = None
            if state.held_until is not None:
                continue
            idle_seconds = now - state.last_access
            if idle_seconds >= self._idle_timeout:
                idle.append((cid, set(state.tab_ids)))
        return idle

    # ── 后台自动关闭 ──

    async def start(self) -> None:
        """启动后台自动关闭任务。"""
        if self._bg_task is not None and not self._bg_task.done():
            return
        self._bg_task = asyncio.create_task(self._auto_close_loop())

    async def stop(self) -> None:
        """停止后台自动关闭任务。"""
        if self._bg_task is not None and not self._bg_task.done():
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None

    async def _auto_close_loop(self) -> None:
        """后台循环：每 60 秒检查一次闲置流并关闭。"""
        while True:
            try:
                await asyncio.sleep(60)
                idle_flows = self._get_idle_flows()
                for chat_flow_id, tab_ids in idle_flows:
                    if self._on_close_flow is not None:
                        try:
                            result = self._on_close_flow(chat_flow_id, tab_ids)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            pass
                    async with self._lock:
                        self._flows.pop(chat_flow_id, None)
            except asyncio.CancelledError:
                return
            except Exception:
                pass

    def reset(self) -> None:
        """重置所有状态（新会话时调用）。"""
        self._flows.clear()
