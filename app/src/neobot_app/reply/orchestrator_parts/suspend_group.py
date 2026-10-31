"""群聊挂起等待（新消息/后台通知/唤醒）。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from ._runtime import asyncio, monotonic_seconds

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue


class SuspendGroupMixin:
    async def _suspend_group_chat(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> tuple[list, str | None, str | None]:
        """挂起等待群聊新消息或后台通知。

        新消息需通过回复意愿判断（@提及或概率命中）才结束挂起。
        - @提及：等待 at_mention_reply_delay_seconds 收集上下文后结束挂起
        - 普通意愿命中：立即结束挂起
        - 后台通知：立即中断挂起
        - 睡眠中：非@消息忽略（不触发回复），@提及唤醒并注入唤醒提示词
        返回 (新消息条目列表, 通知文本或None, 唤醒提示词或None)；
        返回空列表且无通知表示超时。
        """
        from neobot_app.message.fast_reply_keywords import matches_reply_trigger
        from neobot_app.message.queue import QueueEntryType as _QET

        suspend_secs = self._get_group_chat_suspend_wait_seconds()
        at_delay = self._get_at_mention_reply_delay_seconds()
        deadline = monotonic_seconds() + suspend_secs
        all_new_entries: list = []
        notification_text: str | None = None
        wake_prompt: str | None = None
        has_willing = False
        at_mention_deadline = 0.0

        self._logger.debug(
            "群聊挂起循环开始轮询",
            queue_key=queue_key,
            suspend_secs=suspend_secs,
            at_delay=at_delay,
        )
        pipeline_key = f"group:{queue_key}"

        def _has_at_mention(entries: list) -> bool:
            """检查条目列表中是否有@提及消息。"""
            if self._willing_service is None:
                return False
            for entry in entries:
                if entry.kind != _QET.MESSAGE or entry.message is None:
                    continue
                if self._willing_service.is_at_mentioned(entry.message):
                    return True
            return False

        def _at_mention_instant_keyword(entries: list) -> str:
            """被 @ 的条目里是否出现「跳过收集等待」的玩法关键词。

            关键词由插件登记（见 neobot_app.message.fast_reply_keywords）；
            命中即表示意图已经明确，不必再等收集窗口。异常一律降级为空串。
            """
            if self._willing_service is None:
                return ""
            for entry in entries:
                if entry.kind != _QET.MESSAGE or entry.message is None:
                    continue
                try:
                    if not self._willing_service.is_at_mentioned(entry.message):
                        continue
                    keyword = matches_reply_trigger(entry.message)
                except Exception:  # pragma: no cover - 关键词表异常只降级
                    continue
                if keyword:
                    return keyword
            return ""

        def _check_willing(entries: list) -> bool:
            """检查条目列表中是否有任何消息通过回复意愿判断。

            复用 _evaluate_single_message_willing，与正常回复流程使用同一套判断逻辑。
            """
            for entry in entries:
                if entry.kind != _QET.MESSAGE or entry.message is None:
                    continue
                if self._evaluate_single_message_willing(
                    message=entry.message,
                    queue=source,
                    queue_key=queue_key,
                ):
                    return True
            return False

        while monotonic_seconds() < deadline:
            await asyncio.sleep(1.0)
            current_new: list = []
            try:
                current_new = self._collect_new_entries(source, snapshot, queue_key)
            except Exception as exc:
                self._logger.debug(
                    "群聊挂起收集新消息异常",
                    queue_key=queue_key,
                    error=str(exc),
                )
                continue
            if current_new:
                current_new = self._consume_ai_reply_blocked_entries(current_new)
            if current_new:
                # 睡眠拦截:睡眠中非@消息忽略(已入快照,不会反复拾取),
                # @提及唤醒并注入唤醒提示词,与事件入口语义一致
                if self._sleeping():
                    if not self._entries_have_at_mention(current_new, queue_key=queue_key):
                        self._logger.info(
                            "睡眠中,挂起管线忽略新消息",
                            queue_key=queue_key,
                            count=len(current_new),
                        )
                        continue
                    wake_prompt = self._wake_from_sleep() or ""
                    self._logger.info(
                        "睡眠中,挂起管线被@唤醒",
                        queue_key=queue_key,
                    )
                    all_new_entries.extend(current_new)
                    has_willing = True
                    instant_keyword = _at_mention_instant_keyword(current_new)
                    if instant_keyword:
                        self._logger.info(
                            "睡眠中挂起被@命中关键词，跳过收集窗口",
                            queue_key=queue_key,
                            keyword=instant_keyword,
                        )
                        break
                    at_mention_deadline = monotonic_seconds() + at_delay
                    continue
                all_new_entries.extend(current_new)
                if not has_willing:
                    if _check_willing(current_new):
                        has_willing = True
                        if _has_at_mention(current_new):
                            instant_keyword = _at_mention_instant_keyword(current_new)
                            if instant_keyword:
                                # 玩法关键词：意图已经明确，立即结束挂起
                                self._logger.info(
                                    "群聊挂起@提及命中关键词，立即结束挂起",
                                    queue_key=queue_key,
                                    keyword=instant_keyword,
                                )
                                break
                            # @提及：启动延迟收集窗口，不立即break
                            at_mention_deadline = monotonic_seconds() + at_delay
                        else:
                            # 普通意愿命中：立即结束
                            break

            # 轮询后台通知，有通知立即中断挂起
            if notification_text is None:
                notification_text = await self._poll_background_notifications(pipeline_key)

            if notification_text:
                break

            # @提及延迟窗口到期
            if at_mention_deadline > 0 and monotonic_seconds() >= at_mention_deadline:
                break

        self._logger.debug(
            "群聊等待结束",
            event="reply.wait_finished",
            chat_flow_id=pipeline_key,
            reason="notification" if notification_text else "messages" if has_willing else "timeout",
            message_count=len(all_new_entries),
            should_reply=bool(notification_text or has_willing),
        )

        # 通知存在 → 总是返回（通知本身就是触发理由）
        if notification_text:
            return all_new_entries, notification_text, wake_prompt

        # 有意愿消息 → 返回
        if has_willing:
            return all_new_entries, None, wake_prompt

        # 超时且无意愿消息 → 不触发回复
        return [], None, None
