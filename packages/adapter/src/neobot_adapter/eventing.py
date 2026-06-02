from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger, NullLogger

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
                coerced = event

            try:
                if handler.is_async:
                    await handler.handler(coerced)
                else:
                    await asyncio.to_thread(handler.handler, coerced)
            except Exception as exc:
                self._logger.error(f"事件处理失败: {exc}")


def extract_event_model(handler: EventHandlerFunc) -> Optional[type[BaseModel]]:
    try:
        hints = get_type_hints(handler)
    except Exception:
        return None
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


class EventNamespace:
    def __init__(self, adapter: Any, path: tuple[str, ...] = ()) -> None:
        self._adapter = adapter
        self._path = path

    def __getattr__(self, name: str) -> "EventNamespace":
        return EventNamespace(self._adapter, self._path + (name,))

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
