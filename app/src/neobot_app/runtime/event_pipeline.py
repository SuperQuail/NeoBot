from __future__ import annotations

from typing import Any, Dict, List

from neobot_adapter import OneBotAdapter, Subscription
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.utils.parse import safe_parse_model

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.message.process import event_message__to_text
from neobot_app.message.queue import MessageQueue


class EventPipeline:
    def __init__(
        self,
        adapter: OneBotAdapter,
        group_message_queue: MessageQueue,
        friend_message_queue: MessageQueue,
        logger: Logger | None = None,
    ) -> None:
        self.adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
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
        self._friend_queue.push(str(message.user_id or ""), message)
        text = await event_message__to_text(message)
        self._logger.info(f"收到私聊消息: {text}")

    async def _handle_group_message(self, event: Dict[str, Any]) -> None:
        message = safe_parse_model(event, GroupMessage)
        self._group_queue.push(str(message.group_id or ""), message)
        text = await event_message__to_text(message)
        self._logger.info(f"收到群消息[{message.group_id or '未知'}]: {text}")

    async def _handle_notice(self, event: Dict[str, Any]) -> None:
        notice_type = event.get("notice_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{notice_type}" + (f".{sub_type}" if sub_type else "")

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
