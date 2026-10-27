"""消息队列差集、睡眠/待机状态与后台通知轮询。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from neobot_app.reply._utils import entry_fingerprint
from ._runtime import asyncio
if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

class QueueEntriesMixin:
    def is_standby(self) -> bool:
        """Bot 是否处于待机状态。"""
        service = getattr(self, "_standby_service", None)
        return bool(service is not None and service.is_standby())
    def _sleeping(self) -> bool:
        """是否处于睡眠中(群聊不触发回复;私聊不睡眠)。"""
        service = getattr(self, "_sleep_service", None)
        return service is not None and service.is_sleeping()
    def _wake_from_sleep(self) -> str | None:
        """结束睡眠并返回唤醒提示词;未在睡眠时返回 None。"""
        service = getattr(self, "_sleep_service", None)
        if service is None or not service.is_sleeping():
            return None
        service.wake(reason="at_mention_pipeline")
        return service.wake_prompt()
    def _entries_have_at_mention(self, entries: list, *, queue_key: str) -> bool:
        """检查是否有未被硬性屏蔽的 @bot 消息(与睡眠事件入口一致)。"""
        from neobot_app.message.queue import QueueEntryType as _QET

        if self._willing_service is None:
            return False
        for entry in entries:
            if entry.kind != _QET.MESSAGE or entry.message is None:
                continue
            if self._willing_service.is_at_mentioned(entry.message):
                block_reason = self._willing_service.block_reason_for_message(
                    message=entry.message, queue_key=queue_key
                )
                if not block_reason:
                    return True
        return False
    def _collect_new_entries(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> list:
        """收集源队列中比快照新的条目并更新快照。

        使用指纹集合比对，而非位置分割：
        - 指纹在 snapshot 中已存在 → 不是新条目（即使推送顺序与 message_id 顺序不一致）
        - 指纹不在 snapshot 中 → 新条目（支持队列驱逐后的安全回退）
        - 已被命令系统消费的消息（mark_command_consumed）不返回，但仍加入快照，
          避免挂起循环反复拾取；命令回复已由事件入口发出，挂起管线不应再回复
        """
        from neobot_app.message.queue import QueueEntryType

        source_entries = source.entries(queue_key)
        if not source_entries:
            return []

        snapshot_entries = snapshot.entries(queue_key)

        # 收集 snapshot 中所有条目的指纹
        snapshot_fingerprints: set[str] = set()
        for entry in snapshot_entries:
            fp = entry_fingerprint(entry)
            if fp:
                snapshot_fingerprints.add(fp)

        # 在 source 中找出指纹不在 snapshot 中的新条目
        new_entries: list = []
        skipped_consumed: list = []
        for entry in source_entries:
            fp = entry_fingerprint(entry)
            if fp and fp in snapshot_fingerprints:
                continue  # 已存在于快照中
            # 命令系统已消费的消息：跳过注入（仍加入快照，避免反复收集）
            if (
                entry.kind == QueueEntryType.MESSAGE
                and entry.message is not None
                and source.is_command_consumed(queue_key, entry.message.message_id)
            ):
                skipped_consumed.append(entry)
                self._logger.debug(
                    "挂起管线跳过命令已消费消息",
                    queue_key=queue_key,
                    message_id=entry.message.message_id,
                )
                continue
            new_entries.append(entry)

        snapshot.append_entries(queue_key, new_entries + skipped_consumed)

        # 返回全部可渲染的新条目:消息 + 表情回应/戳一戳/撤回(时间戳除外)。
        # 全量构建(role_messages)会渲染这些非消息条目,增量注入必须保持一致,
        # 否则挂起/等待期间到达的回应/戳一戳/撤回会对模型"凭空消失"。
        return [
            entry
            for entry in new_entries
            if entry.kind != QueueEntryType.TIMESTAMP
        ]
    def _consume_ai_reply_blocked_entries(self, entries: list) -> list:
        if self._reply_block_registry is None:
            return entries
        consume = getattr(self._reply_block_registry, "consume_message", None)
        if not callable(consume):
            return entries
        kept = []
        for entry in entries:
            message = getattr(entry, "message", None)
            if message is not None and consume(message):
                self._logger.info("插件监听器已阻止挂起期间私聊消息触发 AI 回复")
                continue
            kept.append(entry)
        return kept
    def _preactivate_cross_chat_tools(
        self, toolset: Any, queue: Any, queue_key: str, event: Any = None,
    ) -> bool:
        """本聊天流收到跨聊天投递时自动加载 cross_chat 工具。

        目标 agent 需要 cross_chat_query/status 查看来源聊天流与任务状态；这些工具
        默认按需加载，等模型自己 skills__load_tools 往往已经错过上下文。
        """
        executor = getattr(toolset, "executor", None)
        if executor is None:
            return False
        activated = getattr(executor, "activated_skill_names", None)
        if callable(activated) and "cross_chat" in activated():
            return False
        hit = False
        background = str(getattr(event, "background_content", "") or "")
        if background.startswith("[跨聊天"):
            hit = True
        if not hit:
            from neobot_app.message.queue import QueueEntryType

            for entry in queue.entries(queue_key):
                if (
                    entry.kind == QueueEntryType.NOTIFICATION
                    and entry.notification is not None
                    and entry.notification.source == "cross_chat"
                ):
                    hit = True
                    break
        if not hit:
            return False
        preactivate = getattr(executor, "preactivate_skills", None)
        if not callable(preactivate):
            return False
        # archive_crud 一起加载：目标 agent 要能按提示读源聊天流的完整档案。
        names = preactivate(["cross_chat", "archive_crud"])
        if names:
            self._logger.info(
                f"检测到跨聊天投递，已自动加载工具：{names}", queue_key=queue_key
            )
        return bool(names)
    async def _poll_background_notifications(self, pipeline_key: str) -> str | None:
        """轮询所有后台通知源，返回通知文本或 None。"""
        try:
            if self._notification_hub is not None:
                notification = await asyncio.wait_for(
                    self._notification_hub.poll(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    self._logger.info(
                        "orchestrator._poll_background_notifications 轮询到通知",
                        pipeline_key=pipeline_key,
                        source=notification.source,
                        preview=notification.content[:120],
                    )
                    return notification.content
                return None

            # 向后兼容：未迁移到统一通知中心的后台管理器
            if self._drawing_manager is not None:
                notification = await asyncio.wait_for(
                    self._drawing_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification

            if self._scheduled_task_manager is not None:
                notification = await asyncio.wait_for(
                    self._scheduled_task_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification

            if self._problem_solver_manager is not None:
                notification = await asyncio.wait_for(
                    self._problem_solver_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification
        except asyncio.TimeoutError:
            self._logger.warning(
                "后台通知轮询超时",
                pipeline_key=pipeline_key,
                timeout_seconds=self._get_dependency_timeout_seconds(),
            )

        return None
