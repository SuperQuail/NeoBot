from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

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


@dataclass(slots=True)
class RuntimeInterceptorRegistration:
    handler: EventHandler
    kind: str | None = None
    stage: str | None = None
    source: str | None = None
    target: str | None = None
    priority: int = 0
    timeout: float | None = None
    logger: Logger = field(default_factory=NullLogger)

    def matches(self, envelope: RuntimeEnvelope) -> bool:
        if self.kind and envelope.kind != self.kind:
            return False
        if self.stage and envelope.stage != self.stage:
            return False
        if self.source and envelope.source != self.source:
            return False
        if self.target and envelope.target != self.target:
            return False
        return True


class PluginHookBus:
    def __init__(
        self,
        *,
        logger: Logger | None = None,
        record_ai_reply_block: ReplyBlockRecorder | None = None,
        output: OutputPort | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._record_ai_reply_block = record_ai_reply_block
        self._output = output or NullOutput()
        self._hooks: list[HookRegistration] = []
        self._interceptors: list[RuntimeInterceptorRegistration] = []
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

    def subscribe_runtime(
        self,
        handler: EventHandler,
        *,
        kind: str | None = None,
        stage: str | None = None,
        source: str | None = None,
        target: str | None = None,
        priority: int = 0,
        timeout: float | None = None,
        logger: Logger | None = None,
    ) -> HookSubscription:
        registration = RuntimeInterceptorRegistration(
            handler=handler,
            kind=kind,
            stage=stage,
            source=source,
            target=target,
            priority=priority,
            timeout=timeout,
            logger=logger or self._logger,
        )
        with self._lock:
            self._interceptors.append(registration)
            self._interceptors.sort(key=lambda item: item.priority, reverse=True)

        def _unsubscribe() -> None:
            with self._lock:
                self._interceptors = [item for item in self._interceptors if item is not registration]

        return HookSubscription(_unsubscribe)

    async def dispatch(self, ctx: Any) -> None:
        event = getattr(ctx, "raw_event", None)
        if not isinstance(event, dict):
            return

        envelope = RuntimeEnvelope(
            kind="inbound_event",
            stage=str(event.get("post_type") or "raw"),
            source="adapter",
            payload={"event": event},
            context={"legacy_context": ctx},
        )
        envelope = await self.dispatch_envelope(envelope)
        updated_event = envelope.payload.get("event")
        if isinstance(updated_event, dict):
            event = updated_event
            try:
                ctx.raw_event = event
            except Exception:
                pass
        if envelope.consumed:
            consume = getattr(ctx, "consume", None)
            if callable(consume):
                consume()
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

    async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
        with self._lock:
            interceptors = [item for item in self._interceptors if item.matches(envelope)]

        for interceptor in interceptors:
            if envelope.consumed:
                break
            result = await self._call_interceptor(interceptor, envelope)
            if isinstance(result, RuntimeEnvelope):
                envelope = result
            elif isinstance(result, dict):
                envelope.payload.update(result)
        return envelope

    async def _call_hook(self, hook: HookRegistration, event: Any) -> bool:
        source = f"plugin_hook.{hook.handler.__module__}.{hook.handler.__qualname__}"
        try:
            with _capture_output(self._output, source=source):
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

    async def _call_interceptor(self, interceptor: RuntimeInterceptorRegistration, envelope: RuntimeEnvelope) -> Any:
        source = f"runtime_interceptor.{interceptor.handler.__module__}.{interceptor.handler.__qualname__}"
        try:
            with _capture_output(self._output, source=source, target=envelope.target):
                call = _call_handler(interceptor.handler, envelope)
                if interceptor.timeout is None:
                    return await call
                return await asyncio.wait_for(call, timeout=interceptor.timeout)
        except TimeoutError:
            interceptor.logger.warning(
                f"插件拦截器处理超时: {interceptor.handler.__module__}.{interceptor.handler.__qualname__}"
            )
            return None
        except Exception as exc:
            interceptor.logger.exception(
                f"插件拦截器处理失败 ({interceptor.handler.__module__}.{interceptor.handler.__qualname__}): {exc}"
            )
            return None


@contextlib.contextmanager
def _capture_output(output: OutputPort, *, source: str, target: str | None = None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        yield
    stdout_text = stdout.getvalue().strip()
    stderr_text = stderr.getvalue().strip()
    if stdout_text:
        output.write(stdout_text, source=source, target=target)
    if stderr_text:
        output.error(stderr_text, source=source, target=target)


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
