"""生命周期与基础设施：后台任务、关闭冲刷、去重、待机门与依赖超时。"""

from __future__ import annotations

import asyncio
from typing import Any
from typing import Dict
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_app.bot_accounts import is_bot_message
from neobot_app.message.addressing import is_addressed_to_bot
from neobot_app.time_context import epoch_seconds


class _PipelineLifecycleMixin:
    async def flush_pending_summaries(self, timeout: float | None = None) -> None:
        """关闭时的收尾：停止派生后台任务、取消在途任务、冲刷未达阈值的摘要。

        `timeout` 是这次冲刷的有界预算（秒）；到点停止继续启动新的总结并记 warning，
        消息仍留在计数器里留给下次启动，所以「少总结几条」不等于丢消息。

        事件订阅由 EventGateway 负责（它才是唯一入口），EventPipeline 不再自己
        订阅：旧实现的 ``start()`` 会再注册一套 ``message``/``notice``/``request``
        订阅，一旦被调用就是同一条事件被投递两次，而它实际上从来没有被调用过。

        ``_stopping`` 在这里一次性置位（关闭流程只会调用一次），此后
        ``_schedule_archive_summary`` 不再派生新的后台任务。
        """
        self._stopping = True
        await self._cancel_background_tasks()
        if self._archive_summary_service is not None:
            await self._archive_summary_service.flush_all(timeout=timeout)

    def _track_background_task(
        self,
        task: asyncio.Task[None],
        *,
        label: str,
        context: dict[str, object] | None = None,
    ) -> None:
        if self._stopping:
            task.cancel()
        self._background_tasks.add(task)

        def _done(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning(
                    f"{label} 后台任务失败",
                    error=str(exc),
                    **(context or {}),
                )

        task.add_done_callback(_done)

    async def _cancel_background_tasks(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    def _has_active_reply_pipeline(self, kind: str, queue_key: str) -> bool:
        if self._reply_orchestrator is None:
            return False
        is_active = getattr(self._reply_orchestrator, "is_pipeline_active", None)
        if callable(is_active):
            return bool(is_active(kind, queue_key))
        return False

    def _get_group_agent_silent_timeout_seconds(self) -> float:
        if self._config is not None:
            value = getattr(
                self._config.chat, "group_agent_silent_timeout_seconds", None
            )
            if isinstance(value, (int, float)):
                return max(0.0, float(value))
        return 120.0

    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0

    async def _handle_inbound_raw_event(self, event: Dict[str, Any]) -> None:
        if self._inbound_pipeline is None:
            return
        try:
            await asyncio.wait_for(
                self._inbound_pipeline.handle_raw_event(event),
                timeout=self._get_dependency_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "入站处理管线超时",
                timeout_seconds=self._get_dependency_timeout_seconds(),
                event_type=event.get("post_type"),
                message_type=event.get("message_type"),
            )
        except Exception as exc:
            self._logger.warning(
                "入站处理管线失败",
                error=str(exc),
                event_type=event.get("post_type"),
                message_type=event.get("message_type"),
            )

    def _schedule_archive_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        if (
            self._stopping
            or self._archive_summary_service is None
            or not conversation_id
        ):
            return

        async def _run() -> None:
            await self._record_archive_summary(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_text=message_text,
                sender_id=sender_id,
                sender_name=sender_name,
            )

        task = asyncio.create_task(_run())
        self._track_background_task(
            task,
            label="archive auto summary",
            context={
                "conversation_kind": conversation_kind,
                "conversation_id": conversation_id,
            },
        )

    async def _record_archive_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        if self._archive_summary_service is None or not conversation_id:
            return
        try:
            await self._archive_summary_service.record_message(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_text=message_text,
                sender_id=sender_id,
                sender_name=sender_name,
            )
        except Exception as exc:
            self._logger.warning(
                "档案自动总结记录失败",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
            )

    def _is_linked_group_duplicate(self, message: Any) -> bool:
        """OneBot 已连接的已映射群：官方通道的同一条群消息交给 OneBot 处理。

        显式 @ 了官方 bot 的消息除外：OneBot 侧没有这个 @，丢给 OneBot 会整条
        丢失（判定走 neobot_app.message.addressing 统一入口）。官方通道断开、
        无映射、OneBot 不在线时都不去重。
        """
        # 解析后 message_type 是枚举（str() 得到 "MessageTypeEnum.group"），先取 value
        message_type = getattr(message, "message_type", None)
        if hasattr(message_type, "value"):
            message_type = message_type.value
        if str(message_type or "") not in ("", "group"):
            return False
        if str(getattr(message, "neobot_channel", "") or "") != "official":
            return False
        group_id = getattr(message, "group_id", None)
        if group_id is None:
            return False
        from neobot_app.user_identity import group_number_for

        if group_number_for(group_id, "official") is None:
            return False
        adapter = getattr(self, "_adapter", None) or getattr(self, "adapter", None)
        connected = getattr(adapter, "connected_channels", None)
        if connected is None:
            return False
        return "onebot" in connected and not is_addressed_to_bot(message, getattr(self, "_config", None))

    async def _is_duplicate_message(
        self, message: PrivateMessage | GroupMessage
    ) -> bool:
        """按 message_id 对真实消息去重：断线重连重投的同一条消息直接丢弃。

        官方通道同一 msg_id 会先推 GROUP_MESSAGE_CREATE（全量、未 @）、后推
        GROUP_AT_MESSAGE_CREATE（@ 事件）；只按 id 去重会把后到的 @ 事件丢掉，
        命令/@ 必回全灭。记录里带上是否 @，仅允许「未 @ → 被 @」升级一次。
        """
        message_id = getattr(message, "message_id", None)
        if message_id is None:
            return False
        addressed = is_addressed_to_bot(message, getattr(self, "_config", None))
        async with self._recent_message_ids_lock:
            for index, (seen_id, seen_addressed) in enumerate(self._recent_message_ids):
                if seen_id != message_id:
                    continue
                if addressed and not seen_addressed:
                    self._recent_message_ids[index] = (message_id, True)
                    return False
                return True
            self._recent_message_ids.append((message_id, addressed))
        return False

    def is_standby(self) -> bool:
        """Bot 是否处于待机状态(待机期间不回复、不触发记忆总结)。"""
        service = getattr(self, "_standby_service", None)
        return bool(service is not None and service.is_standby())

    def _skip_while_standby(
        self, *, kind: str, queue_key: str, message: Any
    ) -> bool:
        """待机熔断:命令已在前面处理完,这里丢掉后续的回复与记忆管线。

        必须在 push/档案总结之前返回,否则待机期间仍会积压记忆总结任务。
        """
        if not self.is_standby():
            return False
        self._logger.info(
            "Bot 已进入待机，消息不进入回复与记忆管线",
            conversation_kind=kind,
            conversation_id=queue_key,
            message_id=getattr(message, "message_id", None),
        )
        return True

    def _is_bot_self(self, message) -> bool:
        """检查消息是否由任一 bot 账号发送；账号解析交给统一提供者。"""
        queue_accounts: set[int] = set()
        for queue in (getattr(self, "_group_queue", None), getattr(self, "_friend_queue", None)):
            queue_accounts.update(getattr(queue, "bot_accounts", None) or ())
        return is_bot_message(message, self._config, queue_accounts)

    @staticmethod
    def _is_message_stale(message, timeout_seconds: float) -> bool:
        """检查消息时间戳是否超过超时秒数。"""
        msg_time = getattr(message, "time", None)
        if msg_time is None:
            return False
        return epoch_seconds() - int(msg_time) > timeout_seconds
