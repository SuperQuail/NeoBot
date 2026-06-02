from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.sandbox import SandboxDataPort

from neobot_adapter.eventing import (
    EventDispatcher,
    EventHandlerFunc,
    EventNamespace,
    Rule,
    Subscription,
    _HandlerRegistration,
    extract_event_model,
)
from neobot_adapter.local.core import LocalCore
from neobot_adapter.model import response
from neobot_adapter.request._proxy import bind_core, unbind_core
from neobot_adapter.utils.parse import safe_parse_model


class LocalAdapter:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8090,
        auth_token: str = "",
        bot_user_id: int = 0,
        bot_name: str = "Neo Bot",
        logger: Optional[Logger] = None,
        packet_callback: Callable[[Dict[str, Any]], None] | None = None,
        sandbox_data: SandboxDataPort | None = None,
    ) -> None:
        self._logger: Logger = logger if logger is not None else NullLogger()
        self._dispatcher = EventDispatcher(self._logger)
        self._core = LocalCore(
            dispatcher=self._dispatcher,
            host=host,
            port=port,
            auth_token=auth_token,
            bot_user_id=bot_user_id,
            bot_name=bot_name,
            logger=self._logger,
            packet_callback=packet_callback,
            sandbox_data=sandbox_data,
        )
        self._packet_callback = packet_callback
        self.on = EventNamespace(self)

    @property
    def core(self) -> LocalCore:
        return self._core

    @property
    def requires_connection_wait(self) -> bool:
        return False

    @property
    def http_url(self) -> str:
        return self._core.http_url

    @property
    def ws_url(self) -> str:
        return self._core.ws_url

    @property
    def on_message(self) -> EventNamespace:
        return self.on.message

    @property
    def on_notice(self) -> EventNamespace:
        return self.on.notice

    @property
    def on_request(self) -> EventNamespace:
        return self.on.request

    @property
    def on_meta_event(self) -> EventNamespace:
        return self.on.meta_event

    async def start(self) -> None:
        bind_core(self._core)
        await self._core.start()

    async def stop(self) -> None:
        await self._core.stop()
        unbind_core()

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        return self._core.wait_for_connection(timeout)

    async def call_api(
        self,
        action: str,
        params: Dict[str, Any],
        timeout: float = 5.0,
    ) -> Optional[Dict[str, Any]]:
        return await self._core.call_api(action, params, timeout)

    def subscribe(
        self,
        event_type: Any,
        handler: EventHandlerFunc,
        **filters: Any,
    ) -> Subscription:
        if isinstance(event_type, str) and "post_type" not in filters:
            filters["post_type"] = event_type
        return self._subscribe(handler, **filters)

    def on_event(
        self,
        func: Optional[EventHandlerFunc] = None,
        *,
        post_type: Optional[str] = None,
        message_type: Optional[str] = None,
        notice_type: Optional[str] = None,
        request_type: Optional[str] = None,
        meta_event_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        rule: Optional[Rule] = None,
        priority: int = 0,
    ) -> Any:
        def decorator(handler: EventHandlerFunc) -> EventHandlerFunc:
            self._register_handler(
                handler,
                post_type=post_type,
                message_type=message_type,
                notice_type=notice_type,
                request_type=request_type,
                meta_event_type=meta_event_type,
                sub_type=sub_type,
                rule=rule,
                priority=priority,
            )
            return handler

        if func is not None:
            return decorator(func)
        return decorator

    async def get_friend_list(self, timeout: float = 5.0) -> response.GetFriendListResponse:
        result = await self.call_api("get_friend_list", {}, timeout)
        return safe_parse_model(result, response.GetFriendListResponse)

    async def get_stranger_info(
        self,
        user_id: int,
        timeout: float = 5.0,
    ) -> response.StrangerInfoResponse:
        result = await self.call_api("get_stranger_info", {"user_id": user_id}, timeout)
        return safe_parse_model(result, response.StrangerInfoResponse)

    async def get_group_list(
        self,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupListResponse:
        result = await self.call_api("get_group_list", {"no_cache": no_cache}, timeout)
        return safe_parse_model(result, response.GetGroupListResponse)

    async def get_group_member_list(
        self,
        group_id: int,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupMemberListResponse:
        result = await self.call_api(
            "get_group_member_list",
            {"group_id": group_id, "no_cache": no_cache},
            timeout,
        )
        return safe_parse_model(result, response.GetGroupMemberListResponse)

    async def get_group_member_info(
        self,
        group_id: int,
        user_id: int,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupMemberInfoResponse:
        result = await self.call_api(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id, "no_cache": no_cache},
            timeout,
        )
        return safe_parse_model(result, response.GetGroupMemberInfoResponse)

    async def get_friend_msg_history(
        self,
        user_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        result = await self.call_api(
            "get_friend_msg_history",
            {
                "user_id": user_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
            timeout,
        )
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_group_msg_history(
        self,
        group_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        result = await self.call_api(
            "get_group_msg_history",
            {
                "group_id": group_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
            timeout,
        )
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_msg(
        self,
        message_id: int,
        timeout: float = 5.0,
    ) -> response.GetSignalMsgResponse:
        result = await self.call_api("get_msg", {"message_id": message_id}, timeout)
        return safe_parse_model(result, response.GetSignalMsgResponse)

    async def get_forward_msg(
        self,
        message_id: str,
        timeout: float = 5.0,
    ) -> dict[str, Any] | None:
        return await self.call_api("get_forward_msg", {"message_id": message_id}, timeout)

    async def send_private_msg(
        self,
        user_id: int,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
    ) -> response.SendMsgResponse:
        if isinstance(message, str):
            payload = {
                "user_id": user_id,
                "message": {"type": "text", "data": {"text": message}},
            }
        else:
            payload = {"user_id": user_id, "message": message}
        result = await self.call_api("send_private_msg", payload, timeout)
        return safe_parse_model(result, response.SendMsgResponse)

    async def send_group_msg(
        self,
        group_id: int,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
    ) -> response.SendMsgResponse:
        if isinstance(message, str):
            payload = {
                "group_id": group_id,
                "message": {"type": "text", "data": {"text": message}},
            }
        else:
            payload = {"group_id": group_id, "message": message}
        result = await self.call_api("send_group_msg", payload, timeout)
        return safe_parse_model(result, response.SendMsgResponse)

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
    ) -> response.SendMsgResponse:
        stored = await self._core.send(conversation, message)
        return safe_parse_model(
            self._core._ok({"message_id": stored.message_id}),
            response.SendMsgResponse,
        )

    def _subscribe(
        self,
        handler: EventHandlerFunc,
        *,
        post_type: Optional[str] = None,
        message_type: Optional[str] = None,
        notice_type: Optional[str] = None,
        request_type: Optional[str] = None,
        meta_event_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        rule: Optional[Rule] = None,
        priority: int = 0,
    ) -> Subscription:
        event_model = extract_event_model(handler)
        registration = _HandlerRegistration(
            handler=handler,
            is_async=inspect.iscoroutinefunction(handler),
            post_type=post_type,
            message_type=message_type,
            notice_type=notice_type,
            request_type=request_type,
            meta_event_type=meta_event_type,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
            event_model=event_model,
        )
        return self._dispatcher.subscribe(registration)

    def _register_handler(self, handler: EventHandlerFunc, **filters: Any) -> None:
        self._subscribe(handler, **filters)

    def _filters_from_path(
        self,
        path: tuple[str, ...],
        *,
        group: bool,
        private: bool,
        sub_type: Optional[str],
    ) -> Dict[str, Optional[str]]:
        filters: Dict[str, Optional[str]] = {
            "post_type": None,
            "message_type": None,
            "notice_type": None,
            "request_type": None,
            "meta_event_type": None,
            "sub_type": sub_type,
        }
        if not path:
            return filters
        root = path[0]
        if root == "message":
            filters["post_type"] = "message"
            if len(path) > 1:
                filters["message_type"] = path[1]
        elif root == "notice":
            filters["post_type"] = "notice"
            if len(path) > 1:
                filters["notice_type"] = path[1]
        elif root == "request":
            filters["post_type"] = "request"
            if len(path) > 1:
                filters["request_type"] = path[1]
        elif root == "meta_event":
            filters["post_type"] = "meta_event"
            if len(path) > 1:
                filters["meta_event_type"] = path[1]
        if group:
            filters["message_type"] = "group"
        if private:
            filters["message_type"] = "private"
        return filters
