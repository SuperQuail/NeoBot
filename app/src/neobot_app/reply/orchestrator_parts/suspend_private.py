"""私聊挂起等待与单条消息意愿评估。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from ._runtime import asyncio, monotonic_seconds

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue


class SuspendPrivateMixin:
    async def _suspend_private_chat(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> tuple[list, str | None]:
        """挂起等待私聊新消息或后台通知。

        首条消息后额外收集一段时间；后台通知会立即中断挂起。
        返回 (新消息条目列表, 通知文本或None)。
        """
        suspend_secs = self._get_private_chat_suspend_wait_seconds()
        collect_secs = self._get_private_chat_new_message_collect_seconds()
        deadline = monotonic_seconds() + suspend_secs
        first_new_time = 0.0
        all_new_entries: list = []
        notification_text: str | None = None

        self._logger.debug(
            "私聊挂起循环开始轮询",
            queue_key=queue_key,
            suspend_secs=suspend_secs,
            collect_secs=collect_secs,
        )
        pipeline_key = f"private:{queue_key}"

        while monotonic_seconds() < deadline:
            await asyncio.sleep(1.0)
            current_new: list = []
            try:
                current_new = self._collect_new_entries(source, snapshot, queue_key)
            except Exception as exc:
                self._logger.debug(
                    "私聊挂起收集新消息异常",
                    queue_key=queue_key,
                    error=str(exc),
                )
                continue
            if current_new:
                current_new = self._consume_ai_reply_blocked_entries(current_new)
            if current_new:
                if not all_new_entries:
                    first_new_time = monotonic_seconds()
                all_new_entries.extend(current_new)

            # 轮询后台通知，有通知立即中断挂起
            if notification_text is None:
                notification_text = await self._poll_background_notifications(pipeline_key)

            if notification_text:
                break

            if all_new_entries:
                elapsed_since_first = monotonic_seconds() - first_new_time
                if elapsed_since_first >= collect_secs:
                    break

        self._logger.debug(
            "私聊等待结束",
            event="reply.wait_finished",
            chat_flow_id=pipeline_key,
            reason="notification" if notification_text else "messages" if all_new_entries else "timeout",
            message_count=len(all_new_entries),
        )
        return all_new_entries, notification_text

    def _evaluate_single_message_willing(
        self,
        *,
        message: Any,
        queue: Any,
        queue_key: str,
    ) -> bool:
        """评估单条消息的回复意愿，与正常回复流程使用完全相同的判断逻辑。

        返回 True 表示应该回复。
        """
        if self._willing_service is None:
            return True

        sender_id = str(getattr(message, "user_id", "?"))
        kind = "group" if getattr(message, "group_id", None) is not None else "private"
        chat_flow_id = f"{kind}:{queue_key}"

        # @提及 → 检查屏蔽后直接通过
        if self._willing_service.is_at_mentioned(message):
            block_reason = self._willing_service.block_reason_for_message(message=message, queue_key=queue_key)
            if block_reason:
                self._logger.debug(
                    "回复意愿判定",
                    event="reply.decided",
                    chat_flow_id=chat_flow_id,
                    should_reply=False,
                    queue_key=queue_key,
                    sender_id=sender_id,
                    reason=block_reason,
                )
                return False
            self._logger.debug(
                "回复意愿判定",
                event="reply.decided",
                chat_flow_id=chat_flow_id,
                should_reply=True,
                reason="at_mention",
                queue_key=queue_key,
                sender_id=sender_id,
            )
            return True

        # 正常意愿评估
        try:
            decision = self._willing_service.evaluate(message=message, queue=queue, queue_key=queue_key)
            self._logger.debug(
                "回复意愿判定",
                event="reply.decided",
                chat_flow_id=chat_flow_id,
                queue_key=queue_key,
                sender_id=sender_id,
                probability=f"{decision.probability:.3f}",
                should_reply=decision.should_reply,
                reasons=list(decision.reasons),
            )
            return decision.should_reply
        except Exception as exc:
            self._logger.warning(
                "回复意愿计算失败，本条消息未唤醒管线",
                event="reply.decision_failed",
                chat_flow_id=chat_flow_id,
                message_id=getattr(message, "message_id", None),
                error_type=type(exc).__name__,
                queue_key=queue_key,
                sender_id=sender_id,
                error=str(exc),
            )
            return False
