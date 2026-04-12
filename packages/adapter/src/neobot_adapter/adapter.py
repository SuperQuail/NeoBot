from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.models import ConversationRef

from neobot_adapter.model import response
from neobot_adapter.receiver.core import AdapterCore
from neobot_adapter.request._proxy import bind_core, unbind_core
from neobot_adapter.request.websocket import WebSocketAPI
from neobot_adapter.utils.parse import safe_parse_model

Rule = Callable[[Dict[str, Any]], bool | Awaitable[bool]]
EventHandlerFunc = Callable[..., Any]


@dataclass
class Subscription:
    _unsubscribe: Callable[[], None]
    _active: bool = True

    def unsubscribe(self) -> None:
        if not self._active:
            return
        self._unsubscribe()
        self._active = False


@dataclass
class _HandlerRegistration:
    handler: EventHandlerFunc
    is_async: bool
    post_type: Optional[str]
    message_type: Optional[str]
    notice_type: Optional[str]
    request_type: Optional[str]
    meta_event_type: Optional[str]
    sub_type: Optional[str]
    rule: Optional[Rule]
    priority: int
    event_model: Optional[type[BaseModel]] = field(default=None)

    def matches(self, event: Dict[str, Any]) -> bool:
        if self.post_type and event.get("post_type") != self.post_type:
            return False
        if self.message_type and event.get("message_type") != self.message_type:
            return False
        if self.notice_type and event.get("notice_type") != self.notice_type:
            return False
        if self.request_type and event.get("request_type") != self.request_type:
            return False
        if self.meta_event_type and event.get("meta_event_type") != self.meta_event_type:
            return False
        if self.sub_type and event.get("sub_type") != self.sub_type:
            return False
        return True

    def coerce(self, event: Dict[str, Any]) -> Any:
        """将原始 dict 转换为 handler 期望的类型。"""
        if self.event_model is not None:
            return self.event_model.model_validate(event)
        return event


class EventDispatcher:
    def __init__(self, logger: Optional[Logger] = None) -> None:
        self._handlers: list[_HandlerRegistration] = []
        self._lock = threading.RLock()
        self._logger: Logger = logger if logger is not None else NullLogger()

    def subscribe(self, registration: _HandlerRegistration) -> Subscription:
        with self._lock:
            self._handlers.append(registration)
            self._handlers.sort(key=lambda item: item.priority, reverse=True)

        def _unsubscribe() -> None:
            with self._lock:
                self._handlers = [
                    item for item in self._handlers if item is not registration
                ]

        return Subscription(_unsubscribe)

    async def publish(self, event: Dict[str, Any]) -> None:
        with self._lock:
            handlers = [handler for handler in self._handlers if handler.matches(event)]

        for handler in handlers:
            if handler.rule is not None:
                try:
                    rule_result = handler.rule(event)
                    if inspect.isawaitable(rule_result):
                        rule_result = await rule_result
                    if not rule_result:
                        continue
                except Exception as exc:
                    self._logger.error(f"事件规则执行失败: {exc}")
                    continue

            try:
                coerced = handler.coerce(event)
            except Exception as exc:
                self._logger.error(f"事件模型转换失败 ({handler.handler.__qualname__}): {exc}")
                coerced = event  # fallback 传原始 dict

            try:
                if handler.is_async:
                    await handler.handler(coerced)
                else:
                    await asyncio.to_thread(handler.handler, coerced)
            except Exception as exc:
                self._logger.error(f"事件处理失败: {exc}")


def _extract_event_model(handler: EventHandlerFunc) -> Optional[type[BaseModel]]:
    """从 handler 的第一个参数类型注解中提取 pydantic 模型类。

    如果注解是 BaseModel 子类，返回该类；否则返回 None（传原始 dict）。
    """
    try:
        hints = get_type_hints(handler)
    except Exception:
        return None
    # 取第一个参数（跳过 self/cls）
    params = list(inspect.signature(handler).parameters.values())
    if not params:
        return None
    first_param = params[0]
    annotation = hints.get(first_param.name)
    if annotation is None:
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


class _EventNamespace:
    def __init__(self, adapter: "OneBotAdapter", path: tuple[str, ...] = ()) -> None:
        self._adapter = adapter
        self._path = path

    def __getattr__(self, name: str) -> "_EventNamespace":
        return _EventNamespace(self._adapter, self._path + (name,))

    def __call__(
        self,
        func: Optional[EventHandlerFunc] = None,
        *,
        group: bool = False,
        private: bool = False,
        rule: Optional[Rule] = None,
        priority: int = 0,
        sub_type: Optional[str] = None,
    ) -> Any:
        filters = self._adapter._filters_from_path(
            self._path,
            group=group,
            private=private,
            sub_type=sub_type,
        )

        def decorator(handler: EventHandlerFunc) -> EventHandlerFunc:
            self._adapter._register_handler(
                handler,
                rule=rule,
                priority=priority,
                **filters,
            )
            return handler

        if func is not None:
            return decorator(func)
        return decorator


class OneBotAdapter:
    def __init__(self, *, max_queue_size: int = 1000, logger: Optional[Logger] = None) -> None:
        self._logger: Logger = logger if logger is not None else NullLogger()
        self._core = AdapterCore(max_queue_size=max_queue_size)
        self._dispatcher = EventDispatcher(self._logger)
        self._dispatch_task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()
        self._api: Optional[WebSocketAPI] = None
        self.on = _EventNamespace(self)

    @property
    def core(self) -> AdapterCore:
        return self._core

    @property
    def api(self) -> WebSocketAPI:
        if self._api is None:
            self._api = WebSocketAPI(self._core)
        return self._api

    @property
    def on_message(self) -> _EventNamespace:
        return self.on.message

    @property
    def on_notice(self) -> _EventNamespace:
        return self.on.notice

    @property
    def on_request(self) -> _EventNamespace:
        return self.on.request

    @property
    def on_meta_event(self) -> _EventNamespace:
        return self.on.meta_event

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

    async def start(self) -> None:
        if self._dispatch_task is not None and not self._dispatch_task.done():
            return
        self._stopping = asyncio.Event()
        bind_core(self._core)
        self._core.start()
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._dispatch_task is not None:
            await self._dispatch_task
            self._dispatch_task = None
        self._core.stop()
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

    async def get_friend_msg_history(
        self,
        user_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        params = {
            "user_id": user_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order,
        }
        result = await self.call_api("get_friend_msg_history", params, timeout)
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_group_msg_history(
        self,
        group_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        params = {
            "group_id": group_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order,
        }
        result = await self.call_api("get_group_msg_history", params, timeout)
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

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
        """统一的消息发送接口"""
        if conversation.kind == "private":
            return await self.send_private_msg(int(conversation.id), message, timeout)
        else:
            return await self.send_group_msg(int(conversation.id), message, timeout)

    async def _dispatch_loop(self) -> None:
        while True:
            if self._stopping.is_set():
                break
            event = await asyncio.to_thread(self._core.get_message, True, 0.1)
            if event is None:
                continue
            await self._dispatcher.publish(event)

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
        event_model = _extract_event_model(handler)
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
