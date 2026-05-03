from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger, NullLogger

Rule = Callable[[dict[str, Any]], bool | Awaitable[bool]]
EventHandler = Callable[..., Any]
ReplyBlockRecorder = Callable[[Any], None]


@dataclass
class HookSubscription:
    _unsubscribe: Callable[[], None]
    _active: bool = True

    def unsubscribe(self) -> None:
        if not self._active:
            return
        self._unsubscribe()
        self._active = False


@dataclass(slots=True)
class HookRegistration:
    handler: EventHandler
    post_type: str | None = None
    message_type: str | None = None
    notice_type: str | None = None
    request_type: str | None = None
    meta_event_type: str | None = None
    sub_type: str | None = None
    rule: Rule | None = None
    priority: int = 0
    timeout: float | None = None
    block: bool = False
    block_ai_reply: bool = False
    logger: Logger = field(default_factory=NullLogger)
    event_model: type[BaseModel] | None = None

    def matches(self, event: dict[str, Any]) -> bool:
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

    def coerce(self, event: dict[str, Any]) -> Any:
        if self.event_model is not None:
            return self.event_model.model_validate(event)
        return event


class PluginHookBus:
    def __init__(
        self,
        *,
        logger: Logger | None = None,
        record_ai_reply_block: ReplyBlockRecorder | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._record_ai_reply_block = record_ai_reply_block
        self._hooks: list[HookRegistration] = []
        self._lock = threading.RLock()

    def subscribe(
        self,
        handler: EventHandler,
        *,
        post_type: str | None = None,
        message_type: str | None = None,
        notice_type: str | None = None,
        request_type: str | None = None,
        meta_event_type: str | None = None,
        sub_type: str | None = None,
        rule: Rule | None = None,
        priority: int = 0,
        timeout: float | None = None,
        block: bool = False,
        block_ai_reply: bool = False,
        logger: Logger | None = None,
    ) -> HookSubscription:
        registration = HookRegistration(
            handler=handler,
            post_type=post_type,
            message_type=message_type,
            notice_type=notice_type,
            request_type=request_type,
            meta_event_type=meta_event_type,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            logger=logger or self._logger,
            event_model=_extract_event_model(handler),
        )
        with self._lock:
            self._hooks.append(registration)
            self._hooks.sort(key=lambda item: item.priority, reverse=True)

        def _unsubscribe() -> None:
            with self._lock:
                self._hooks = [item for item in self._hooks if item is not registration]

        return HookSubscription(_unsubscribe)

    async def dispatch(self, ctx: Any) -> None:
        event = getattr(ctx, "raw_event", None)
        if not isinstance(event, dict):
            return
        with self._lock:
            hooks = [hook for hook in self._hooks if hook.matches(event)]

        for hook in hooks:
            if getattr(ctx, "consumed", False):
                break
            if hook.rule is not None:
                try:
                    rule_result = hook.rule(event)
                    if inspect.isawaitable(rule_result):
                        rule_result = await rule_result
                    if not rule_result:
                        continue
                except Exception as exc:
                    hook.logger.exception(f"插件事件规则执行失败 ({hook.handler.__module__}.{hook.handler.__qualname__}): {exc}")
                    continue

            try:
                payload = hook.coerce(event)
            except Exception as exc:
                hook.logger.exception(f"插件事件模型转换失败 ({hook.handler.__module__}.{hook.handler.__qualname__}): {exc}")
                payload = event

            handled = await self._call_hook(hook, payload)
            if not handled:
                continue

            if hook.block_ai_reply:
                block_ai_reply = getattr(ctx, "block_ai_reply", None)
                if callable(block_ai_reply):
                    block_ai_reply()
                if self._record_ai_reply_block is not None:
                    self._record_ai_reply_block(event)
            if hook.block:
                consume = getattr(ctx, "consume", None)
                if callable(consume):
                    consume()
                break

    async def _call_hook(self, hook: HookRegistration, event: Any) -> bool:
        try:
            call = _call_handler(hook.handler, event)
            if hook.timeout is None:
                await call
            else:
                await asyncio.wait_for(call, timeout=hook.timeout)
            return True
        except TimeoutError:
            hook.logger.warning(f"插件事件处理超时: {hook.handler.__module__}.{hook.handler.__qualname__}")
            return False
        except Exception as exc:
            hook.logger.exception(f"插件事件处理失败 ({hook.handler.__module__}.{hook.handler.__qualname__}): {exc}")
            return False


def _extract_event_model(handler: EventHandler) -> type[BaseModel] | None:
    try:
        hints = get_type_hints(handler)
    except Exception:
        return None
    params = list(inspect.signature(handler).parameters.values())
    if not params:
        return None
    annotation = hints.get(params[0].name)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


async def _call_handler(handler: EventHandler, event: Any) -> Any:
    if inspect.iscoroutinefunction(handler):
        return await handler(event)
    return await asyncio.to_thread(handler, event)
