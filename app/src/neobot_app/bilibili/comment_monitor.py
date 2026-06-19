"""B站评论区异步监控器 — 仅通过 reply_feed 监控"回复我的"评论。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BilibiliCommentMonitor:
    """B站评论区异步监控器（仅 reply_feed）。"""

    def __init__(self, client, config, bridge):
        from .client import BilibiliClient
        from .event_bridge import BilibiliEventBridge

        self.client: BilibiliClient = client
        self.config = config
        self.bridge: BilibiliEventBridge = bridge
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_reply_feed_check = 0.0
        self._processed_ids: set[int] = set()
        self._program_start_time = int(time.time())

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("B站评论监控器: 已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("B站评论监控器: 已停止")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                bilibili_cfg = getattr(self.config, "bilibili", None)
                interval = bilibili_cfg.poll_interval_seconds if bilibili_cfg else 60.0

                if now - self._last_reply_feed_check >= interval:
                    await self._check_reply_feed()
                    self._last_reply_feed_check = now

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("B站评论监控异常")
            await asyncio.sleep(1.0)

    async def _check_reply_feed(self) -> None:
        """检查'回复我的'通知。"""
        bilibili_cfg = getattr(self.config, "bilibili", None)
        if not bilibili_cfg or not bilibili_cfg.comment_reply_enabled:
            return

        items = await asyncio.to_thread(self.client.get_reply_feed, limit=20)
        if not items:
            return

        for item in items:
            if not self._running:
                break
            try:
                await self._process_reply_feed_item(item)
            except Exception:
                logger.exception("处理 reply_feed 条目失败")

    async def _process_reply_feed_item(self, item: dict) -> None:
        """处理'回复我的'单条条目。"""
        reply_id = item.get("id") or 0
        reply_time = item.get("reply_time") or 0

        if reply_id in self._processed_ids:
            return
        if reply_time < self._program_start_time:
            return
        self._processed_ids.add(reply_id)

        await self.bridge.handle_new_comment(item, source="reply_feed")

    @property
    def is_running(self) -> bool:
        return self._running
