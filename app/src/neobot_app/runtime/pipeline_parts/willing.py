"""回复意愿：睡眠拦截、@ 直回、图片等待锁与回复后队列。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_app.message.queue import MessageQueue
from neobot_app.willing.models import WillingDecision

from .helpers import _message_has_images


class _PipelineWillingMixin:
    async def _handle_sleeping_message(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        chat_type: str,
    ) -> bool:
        """睡眠中的群消息处理:仅被@可唤醒回复,其余消息只入队不触发回复。"""
        at_mentioned = self._willing_service is not None and self._willing_service.is_at_mentioned(message)
        if not at_mentioned:
            self._logger.debug(
                "睡眠中，消息已入队",
                event="reply.decided",
                should_reply=False,
                reason="sleeping",
                chat_flow_id=f"group:{queue_key}",
                conversation_kind="group",
                conversation_id=queue_key,
            )
            return False

        # 硬性屏蔽优先于唤醒:被屏蔽的会话即使@也不回复
        if self._willing_service is not None:
            block_reason = self._willing_service.block_reason_for_message(
                message=message,
                queue_key=queue_key,
            )
            if block_reason:
                self._logger.debug(
                    "回复意愿判定",
                    event="reply.decided",
                    chat_flow_id=f"group:{queue_key}",
                    message_id=message.message_id,
                    conversation_kind="group",
                    conversation_id=queue_key,
                    probability=0.0,
                    should_reply=False,
                    reasons=f"原因: 已屏蔽: {block_reason}",
                )
                return False

        # 被@唤醒:结束睡眠并注入唤醒提示词回复
        self._sleep_service.wake(reason="at_mention_event")
        delay = 5.0
        if self._config is not None:
            val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                delay = float(val)
        # 玩法关键词同样跳过唤醒后的收集等待（意图明确，没必要再拖）
        instant_keyword = self._at_mention_instant_keyword(message)
        if instant_keyword:
            self._logger.info(
                "睡眠中被@命中关键词，跳过唤醒等待",
                queue_key=queue_key,
                keyword=instant_keyword,
                delay_seconds=delay,
            )
        elif delay > 0:
            self._logger.debug(
                "睡眠中被@唤醒,延迟回复等待中",
                queue_key=queue_key,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

        decision = WillingDecision(
            manager_name="wake_up",
            probability=1.0,
            should_reply=True,
            reasons=("睡眠中被@唤醒,直接回复",),
        )
        self._logger.debug(
            "回复意愿判定",
            event="reply.decided",
            chat_flow_id=f"group:{queue_key}",
            message_id=message.message_id,
            conversation_kind="group",
            conversation_id=queue_key,
            probability=1.0,
            should_reply=True,
            reasons="原因: 睡眠中被@唤醒,注入唤醒提示词",
        )
        if self._reply_orchestrator is None:
            return False
        return self._start_reply_with_tracking(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            background_content=self._sleep_service.wake_prompt(),
        )

    @asynccontextmanager
    async def _image_willing_lock(self, queue_key: str) -> AsyncIterator[asyncio.Lock]:
        """按 queue_key 分片的图片意愿处理锁：只保护取列表/清理阶段。"""
        while True:
            lock = self._image_willing_locks.get(queue_key)
            if lock is None:
                lock = asyncio.Lock()
                self._image_willing_locks[queue_key] = lock
            await lock.acquire()
            if self._image_willing_locks.get(queue_key) is lock:
                break
            lock.release()
        try:
            yield lock
        finally:
            if self._image_willing_locks.get(queue_key) is lock:
                del self._image_willing_locks[queue_key]
            lock.release()

    async def _process_pending_image_willing(self, queue_key: str) -> None:
        """等待图片解析完成，然后按序处理待处理队列。若触发回复则清空剩余。"""
        try:
            if self._image_parse_service is not None:
                await self._image_parse_service.wait_for_queue(
                    queue_key,
                    timeout=self._get_group_agent_silent_timeout_seconds(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 等待失败也必须继续往下走：旧实现直接抛出会让 pending 列表既不
            # 被取出也不被处理，这些消息会永久滞留（不再触发回复）。
            self._logger.warning(
                "等待图片解析失败，继续处理待处理消息",
                queue_key=queue_key,
                error=str(exc),
            )

        async with self._image_willing_lock(queue_key):
            pending = self._pending_image_willing.pop(queue_key, [])
        if not pending:
            return

        for msg in pending:
            if queue_key in self._replying_queues and not self._has_active_reply_pipeline("group", queue_key):
                self._logger.warning(
                    "已清理过期的回复中队列状态",
                    queue_key=queue_key,
                    kind="group",
                )
                self._replying_queues.discard(queue_key)
            if queue_key in self._replying_queues:
                # 已在回复中，剩余消息放入 post-reply 队列
                idx = pending.index(msg)
                if idx >= 0:
                    self._post_reply_willing.setdefault(queue_key, []).extend(pending[idx:])
                break

            triggered = await self._handle_willing_decision(message=msg, queue=self._group_queue, queue_key=queue_key)
            if triggered:
                break

    async def _process_post_reply_queue(self, queue_key: str) -> None:
        """回复结束后依次处理期间收到的新消息。"""
        pending = self._post_reply_willing.pop(queue_key, [])
        if not pending:
            return

        timeout = 60.0
        if self._config is not None:
            val = getattr(self._config.chat, "post_reply_message_timeout_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                timeout = float(val)

        self._logger.debug(
            "处理回复期间积压的消息",
            chat_flow_id=f"group:{queue_key}",
            queue_key=queue_key,
            count=len(pending),
        )

        for msg in pending:
            if queue_key in self._replying_queues and not self._has_active_reply_pipeline("group", queue_key):
                self._logger.warning(
                    "已清理过期的回复中队列状态",
                    queue_key=queue_key,
                    kind="group",
                )
                self._replying_queues.discard(queue_key)
            if queue_key in self._replying_queues:
                self._post_reply_willing.setdefault(queue_key, []).extend(pending[pending.index(msg) :])
                return

            if timeout > 0 and self._is_message_stale(msg, timeout):
                self._logger.debug(
                    "回复后队列消息超时跳过",
                    queue_key=queue_key,
                    msg_time=getattr(msg, "time", None),
                )
                continue

            if _message_has_images(msg):
                self._pending_image_willing.setdefault(queue_key, []).append(msg)
                await self._process_pending_image_willing(queue_key)
            else:
                await self._handle_willing_decision(message=msg, queue=self._group_queue, queue_key=queue_key)
