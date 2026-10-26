"""关闭时冲刷：并行触发所有未达间隔的计数器总结（有界预算）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .constants import COUNTER_TABLE
from .helpers import _consume_flush_result, _settled_flush_result, _unfinished_flush_count


class SummaryFlushMixin:
    """进程关闭路径使用的计数器冲刷。"""

    async def flush_all(self, timeout: float | None = None) -> None:
        """关闭时并发刷新所有待处理的计数器。

        遍历每个存在未摘要消息（count > 0）但尚未达到配置间隔的计数器，
        立即触发摘要，确保退出时消息不丢失。

        `timeout` 给这次冲刷一个有界预算：调用方是进程关闭，不能无限期挂在这里。
        到点只是停止**继续启动**新的总结并记 warning；已经启动的那些由
        `_summarize_and_reset` 复位计数器（成功）或保留消息（失败），所以最坏情况
        是少总结几条，消息仍在计数器里留给下次，不会丢。
        """
        try:
            items = await self._archive.list(
                COUNTER_TABLE, tags=["auto_summary_counter"], limit=10_000,
            )
        except Exception as exc:
            self._logger.warning(
                "档案自动总结刷新：列举计数器失败",
                error=str(exc),
            )
            return

        semaphore = asyncio.Semaphore(50)

        async def _flush_one(item: Any) -> bool:
            if not item.key or not item.value:
                return False
            try:
                parts = item.key.split(":", 1)
                if len(parts) != 2:
                    return False
                conversation_kind, conversation_id = parts
                if conversation_kind not in ("group", "private"):
                    return False

                state = json.loads(item.value)
                count = int(state.get("count", 0))
                interval = self._interval_for(conversation_kind)
                if count <= 0 or count >= interval:
                    return False

                messages = state.get("messages", [])
                if not messages:
                    return False

                counter_key = item.key
                async with semaphore:
                    # 只在锁内读最新状态并判断条件；总结本身不持锁——
                    # 持锁跑模型会让总结期间每条消息都卡在这把锁上。
                    async with self._counter_lock(counter_key):
                        current = await self._load_counter(counter_key)
                        current_count = int(current.get("count", 0))
                        if current_count <= 0 or current_count >= interval:
                            return False
                        current_messages = list(current.get("messages", []))
                        if not current_messages:
                            return False
                    return await self._summarize_and_reset(
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        counter_key=counter_key,
                        messages=current_messages,
                        snapshot_count=current_count,
                    )
            except Exception as exc:
                self._logger.warning(
                    "档案自动总结刷新：处理计数器失败",
                    key=item.key,
                    error=str(exc),
                )
                return False

        tasks = [asyncio.create_task(_flush_one(item)) for item in items]
        if timeout is None:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            _done, pending = await asyncio.wait(tasks, timeout=timeout)
            # 到点不取消收尾：写档案是最后一步，取消会留下谁都没清的中间态。改为让它们
            # 跑完并消费结果，避免「exception was never retrieved」。
            for task in pending:
                task.add_done_callback(_consume_flush_result)
            # 与 gather(return_exceptions=True) 同语义：失败的记 None，不在此处抛出。
            results = [_settled_flush_result(task) for task in tasks]
        unfinished = _unfinished_flush_count(tasks)
        flushed = sum(1 for r in results if r is True)

        if flushed:
            self._logger.info(
                "关闭时已刷新档案自动总结",
                flushed_count=flushed,
            )
        if unfinished:
            self._logger.warning(
                "关闭时档案自动总结超出预算，已停止等待",
                unfinished_count=unfinished,
                timeout_seconds=timeout,
            )
