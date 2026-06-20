"""B站私信轮询监控器（异步适配版）。

复用 dev-test 中已验证的 Monitor 逻辑，包装为 asyncio 兼容。
"""

from __future__ import annotations

import asyncio
from loguru import logger
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional



@dataclass
class PrivateMonitorConfig:
    """私信监控器配置。"""
    session_check_count: int = 20
    message_check_interval: float = 1.0
    min_poll_interval: float = 60.0  # 两次完整轮询间隔
    default_reply_enabled: bool = False
    default_reply_message: str = "感谢留言~"
    ai_reply_enabled: bool = True
    # 回调由 BilibiliEventBridge 设置


class BilibiliPrivateMonitor:
    """B站私信异步监控器。"""

    def __init__(self, client, config, bridge):
        from .client import BilibiliClient
        from .event_bridge import BilibiliEventBridge

        self.client: BilibiliClient = client
        self.config = config
        self.bridge: BilibiliEventBridge = bridge
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_poll_time = 0.0
        self._processed_ids: set[str] = set()
        self._program_start_time = int(time.time())

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("B站私信监控器: 已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("B站私信监控器: 已停止")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                if now - self._last_poll_time >= self.config.bilibili.poll_interval_seconds:
                    await self._poll_sessions()
                    self._last_poll_time = now
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("B站私信监控异常")
            await asyncio.sleep(1.0)

    async def _poll_sessions(self) -> None:
        """轮询私信会话。"""
        bilibili_cfg = getattr(self.config, "bilibili", None)
        if not bilibili_cfg or not bilibili_cfg.private_message_enabled:
            return

        sessions = await asyncio.to_thread(
            self.client.get_sessions, count=self.session_check_count
        )
        if not sessions:
            return

        for session in sessions:
            if not self._running:
                break
            try:
                await self._process_session(session)
            except Exception:
                logger.exception("处理私信会话失败: talker={}", getattr(session, "talker_id", "?"))

    async def _process_session(self, session) -> None:
        """处理单个会话的新消息。"""
        messages = await asyncio.to_thread(
            self.client.get_new_messages, session
        )
        if not messages:
            return

        for msg in messages:
            if not self._running:
                break
            # 跳过自己的消息
            if msg.sender_uid == self.client.my_uid:
                continue
            # 跳过启动前的旧消息（防止重启后重复回复）
            if msg.timestamp and msg.timestamp < self._program_start_time - 300:
                continue
            # 去重
            if msg.msg_key and msg.msg_key in self._processed_ids:
                continue
            if msg.msg_key:
                self._processed_ids.add(msg.msg_key)

            await self.bridge.handle_new_private_message(msg, session)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_check_count(self) -> int:
        return getattr(
            getattr(self.config, "bilibili", None),
            "session_check_count",
            20,
        )
