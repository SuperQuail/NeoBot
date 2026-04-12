from __future__ import annotations

from typing import Any, Dict, List

from neobot_adapter import OneBotAdapter, Subscription
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.model.notice import GroupMessageDelete, PrivateMessageDelete
from neobot_adapter.utils.parse import safe_parse_model

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.message.process import event_message__to_text
from neobot_app.message.queue import MessageQueue
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService


class EventPipeline:
    def __init__(
        self,
        adapter: OneBotAdapter,
        group_message_queue: MessageQueue,
        friend_message_queue: MessageQueue,
        profile_service: UserProfileService | None = None,
        willing_service: WillingService | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._profile_service = profile_service
        self._willing_service = willing_service
        self._logger = logger or NullLogger()
        self._subscriptions: List[Subscription] = []
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        self._subscriptions = [
            self.adapter.subscribe(
                "message",
                self._handle_private_message,
                message_type="private",
            ),
            self.adapter.subscribe(
                "message",
                self._handle_group_message,
                message_type="group",
            ),
            self.adapter.subscribe(
                "notice",
                self._handle_notice,
            ),
            self.adapter.subscribe(
                "request",
                self._handle_request,
            ),
        ]
        self._started = True
        self._logger.info("实时事件管线已启动")

    def stop(self) -> None:
        if not self._started:
            return

        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()
        self._started = False
        self._logger.info("实时事件管线已停止")

    async def _handle_private_message(self, event: Dict[str, Any]) -> None:
        message = safe_parse_model(event, PrivateMessage)
        queue_key = str(message.user_id or "")
        self._friend_queue.push(queue_key, message)
        await self._refresh_profile_for_message(message)
        text = await event_message__to_text(message)
        self._log_willing_decision(message=message, queue=self._friend_queue, queue_key=queue_key)
        self._logger.info(f"收到私聊消息: {text}")

    async def _handle_group_message(self, event: Dict[str, Any]) -> None:
        message = safe_parse_model(event, GroupMessage)
        queue_key = str(message.group_id or "")
        self._group_queue.push(queue_key, message)
        await self._refresh_profile_for_message(message)
        text = await event_message__to_text(message)
        self._log_willing_decision(message=message, queue=self._group_queue, queue_key=queue_key)
        self._logger.info(f"收到群消息[{message.group_id or '未知'}]: {text}")

    def _log_willing_decision(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        if self._willing_service is None or not queue_key:
            return

        conversation_type = "group" if isinstance(message, GroupMessage) else "private"
        try:
            decision = self._willing_service.evaluate(
                message=message,
                queue=queue,
                queue_key=queue_key,
            )
        except Exception as exc:
            self._logger.warning(
                "回复意愿计算失败",
                conversation_type=conversation_type,
                conversation_id=queue_key,
                error=str(exc),
            )
            return

        self._logger.info(
            "回复意愿",
            conversation_type=conversation_type,
            conversation_id=queue_key,
            manager=decision.manager_name,
            probability=f"{decision.probability:.3f}",
            should_reply=decision.should_reply,
            reasons=" | ".join(decision.reasons),
        )

    async def _refresh_profile_for_message(
        self,
        message: PrivateMessage | GroupMessage,
    ) -> None:
        if self._profile_service is None or message.user_id is None:
            return

        observed_fields: dict[str, Any] = {}
        if message.sender is not None:
            if message.sender.nickname:
                observed_fields["nick_name"] = message.sender.nickname
            if message.sender.sex is not None:
                observed_fields["sex"] = getattr(message.sender.sex, "value", message.sender.sex)

        try:
            await self._profile_service.ensure_user_profile(
                str(message.user_id),
                observed_fields=observed_fields,
            )
        except Exception as exc:
            self._logger.warning(
                "刷新消息发送者资料失败",
                user_id=message.user_id,
                error=str(exc),
            )

    async def _handle_notice(self, event: Dict[str, Any]) -> None:
        notice_type = event.get("notice_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{notice_type}" + (f".{sub_type}" if sub_type else "")
        if notice_type in {"private_message_delete", "friend_recall"}:
            notice = safe_parse_model(event, PrivateMessageDelete)
            queue_key = str(notice.user_id or "")
            if queue_key:
                self._friend_queue.push_notice(queue_key, notice)
        elif notice_type in {"group_message_delete", "group_recall"}:
            notice = safe_parse_model(event, GroupMessageDelete)
            queue_key = str(notice.group_id or "")
            if queue_key:
                self._group_queue.push_notice(queue_key, notice)

        # 构建详情
        details: list[str] = []
        for key in ("user_id", "operator_id", "sender_id", "target_id",
                     "group_id", "message_id", "file", "duration",
                     "honor_type", "title", "card_new", "card_old"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到通知[{label}] {info}".rstrip())

    async def _handle_request(self, event: Dict[str, Any]) -> None:
        request_type = event.get("request_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{request_type}" + (f".{sub_type}" if sub_type else "")

        details: list[str] = []
        for key in ("user_id", "group_id", "comment", "flag"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到请求[{label}] {info}".rstrip())
