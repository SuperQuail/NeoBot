from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger

from neobot_modloader.bot import Bot
from neobot_modloader.command_dsl import MessagePattern, PatternError, PatternMatch
from neobot_modloader.message import Message
from neobot_modloader.reply import Reply


Handler = Callable[..., Any]


@dataclass(slots=True)
class _Registration:
    kind: str
    pattern: MessagePattern
    handler: Handler
    priority: int
    block: bool
    block_ai_reply: bool
    timeout: float | None
    parse_error: str
    group: bool = False
    private: bool = False
    text: str | None = None
    contains: str | Sequence[str] | None = None
    keywords: str | Sequence[str] | None = None
    regex: str | re.Pattern[str] | None = None
    startswith: str | None = None
    endswith: str | None = None
    fullmatch: str | None = None
    rule: Callable[[dict[str, Any]], Any] | None = None


class Plugin:
    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        description: str = "",
        usage: str = "",
        author: str = "",
        config: type[BaseModel] | None = None,
        dependencies: Sequence[str] = (),
        priority: int = 0,
        min_neobot_version: str | None = None,
        python_dependencies: Sequence[str] = (),
    ) -> None:
        self.name = _validate_name(name)
        self.version = str(version)
        self.description = description
        self.usage = usage
        self.author = author
        self.config_model = config
        self.dependencies = tuple(dependencies)
        self.priority = int(priority)
        self.min_neobot_version = min_neobot_version
        self.python_dependencies = tuple(python_dependencies)
        self._registrations: list[_Registration] = []
        self._load_handlers: list[Handler] = []
        self._startup_handlers: list[Handler] = []
        self._shutdown_handlers: list[Handler] = []
        self._context: Any | None = None
        self._config: BaseModel | None = None
        self._bound = False

    def command(
        self,
        pattern: str,
        *,
        aliases: Sequence[str] | None = None,
        priority: int = 10,
        block: bool = True,
        timeout: float | None = None,
        parse_error: str = "reply",
    ) -> Callable[[Handler], Handler]:
        compiled = MessagePattern(pattern, command=True, aliases=tuple(aliases or ()))
        _validate_parse_error(parse_error)

        def decorate(handler: Handler) -> Handler:
            self._registrations.append(
                _Registration(
                    kind="command",
                    pattern=compiled,
                    handler=handler,
                    priority=priority,
                    block=block,
                    block_ai_reply=False,
                    timeout=timeout,
                    parse_error=parse_error,
                )
            )
            return handler

        return decorate

    def message(
        self,
        pattern: str | None = None,
        *,
        text: str | None = None,
        contains: str | Sequence[str] | None = None,
        keywords: str | Sequence[str] | None = None,
        regex: str | re.Pattern[str] | None = None,
        startswith: str | None = None,
        endswith: str | None = None,
        fullmatch: str | None = None,
        group: bool = False,
        private: bool = False,
        rule: Callable[[dict[str, Any]], Any] | None = None,
        priority: int = 10,
        block: bool = False,
        block_ai_reply: bool = False,
        timeout: float | None = None,
        parse_error: str = "ignore",
    ) -> Callable[[Handler], Handler]:
        if group and private:
            raise ValueError("group and private cannot both be True")
        _validate_parse_error(parse_error)
        compiled = MessagePattern(pattern, command=False)

        def decorate(handler: Handler) -> Handler:
            self._registrations.append(
                _Registration(
                    kind="message",
                    pattern=compiled,
                    handler=handler,
                    priority=priority,
                    block=block,
                    block_ai_reply=block_ai_reply,
                    timeout=timeout,
                    parse_error=parse_error,
                    group=group,
                    private=private,
                    text=text,
                    contains=contains,
                    keywords=keywords,
                    regex=regex,
                    startswith=startswith,
                    endswith=endswith,
                    fullmatch=fullmatch,
                    rule=rule,
                )
            )
            return handler

        return decorate

    def on_load(self, value: Any) -> Any:
        if callable(value) and not _looks_like_context(value):
            self._load_handlers.append(value)
            return value
        return self._load(value)

    def on_startup(self, handler: Handler) -> Handler:
        self._startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Handler) -> Handler:
        self._shutdown_handlers.append(handler)
        return handler

    async def on_start(self) -> None:
        for handler in self._startup_handlers:
            await self._call_lifecycle(handler)

    async def on_stop(self) -> None:
        for handler in reversed(self._shutdown_handlers):
            await self._call_lifecycle(handler)
        self._bound = False

    async def _load(self, context: Any) -> None:
        self._context = context
        self._config = self.config_model.model_validate(dict(context.config)) if self.config_model is not None else None
        if not self._bound:
            self._bind_handlers(context)
            self._bound = True
        for handler in self._load_handlers:
            await self._call_lifecycle(handler)

    def _bind_handlers(self, context: Any) -> None:
        for registration in self._registrations:
            subscription = context.hook_bus.subscribe(
                self._wrap_handler(registration, context),
                post_type="message",
                message_type=_message_type_filter(registration),
                rule=self._build_rule(registration),
                priority=registration.priority,
                timeout=registration.timeout,
                block=registration.block,
                block_ai_reply=registration.block_ai_reply,
                logger=context.logger,
            )
            context.record_subscription(subscription)

    def _build_rule(self, registration: _Registration) -> Callable[[dict[str, Any]], Any]:
        async def rule(event: dict[str, Any]) -> bool:
            message = Message(event)
            if registration.kind == "command":
                return registration.pattern.match(message).command_matched
            pattern_match = registration.pattern.match(message)
            if not pattern_match.matched:
                return False
            if not _message_filters_match(registration, event, message):
                return False
            if registration.rule is None:
                return True
            result = registration.rule(event)
            if inspect.isawaitable(result):
                result = await result
            return bool(result)

        return rule

    def _wrap_handler(self, registration: _Registration, context: Any) -> Handler:
        async def dispatch(event: dict[str, Any]) -> None:
            message = Message(event)
            match = registration.pattern.match(message)
            if not match.matched:
                await _handle_parse_error(registration, context, event, match)
                return
            await self._call_handler(registration.handler, context, event, message, match.values)

        return dispatch

    async def _call_lifecycle(self, handler: Handler) -> Any:
        if self._context is None:
            return None
        return await self._call_handler(handler, self._context, {}, Message({}), {})

    async def _call_handler(
        self,
        handler: Handler,
        context: Any,
        event: dict[str, Any],
        message: Message,
        captures: dict[str, Any],
    ) -> Any:
        kwargs = await _resolve_handler_kwargs(
            handler,
            context=context,
            event=event,
            message=message,
            captures=captures,
            config=self._config,
            config_model=self.config_model,
        )
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


async def _resolve_handler_kwargs(
    handler: Handler,
    *,
    context: Any,
    event: dict[str, Any],
    message: Message,
    captures: dict[str, Any],
    config: BaseModel | None,
    config_model: type[BaseModel] | None,
) -> dict[str, Any]:
    try:
        hints = get_type_hints(handler, include_extras=False)
    except Exception:
        hints = {}
    signature = inspect.signature(handler)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in {inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL}:
            continue
        annotation = hints.get(name)
        if name in captures:
            kwargs[name] = captures[name]
        elif annotation is Reply:
            kwargs[name] = Reply(context, event)
        elif annotation is Message:
            kwargs[name] = message
        elif annotation is Bot:
            kwargs[name] = Bot(context.adapter)
        elif annotation is Logger or name == "logger":
            kwargs[name] = context.logger
        elif annotation is Path and name == "data_dir":
            kwargs[name] = context.data_dir
        elif annotation is Path and name == "plugin_dir":
            kwargs[name] = context.plugin_dir
        elif name == "event":
            kwargs[name] = event
        elif name == "plugins":
            kwargs[name] = context.plugins
        elif name == "host":
            kwargs[name] = context.plugin_host
        elif config_model is not None and annotation is config_model:
            kwargs[name] = config
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"Cannot resolve parameter {name!r} for handler {handler.__qualname__}")
    return kwargs


async def _handle_parse_error(registration: _Registration, context: Any, event: dict[str, Any], match: PatternMatch) -> None:
    if registration.parse_error == "ignore":
        return
    if registration.parse_error == "raise":
        raise PatternError(match.error or "pattern parse failed")
    reply = Reply(context, event)
    await reply.send(f"参数错误，用法: {registration.pattern.usage}")


def _message_type_filter(registration: _Registration) -> str | None:
    if registration.group:
        return "group"
    if registration.private:
        return "private"
    return None


def _message_filters_match(registration: _Registration, event: dict[str, Any], message: Message) -> bool:
    text_value = message.text
    if registration.text is not None and text_value != registration.text:
        return False
    contains_values = _text_list(registration.contains)
    if contains_values and not all(value in text_value for value in contains_values):
        return False
    keyword_values = _text_list(registration.keywords)
    if keyword_values and not any(value in text_value for value in keyword_values):
        return False
    if registration.startswith is not None and not text_value.startswith(registration.startswith):
        return False
    if registration.endswith is not None and not text_value.endswith(registration.endswith):
        return False
    if registration.fullmatch is not None and text_value != registration.fullmatch:
        return False
    if registration.regex is not None:
        pattern = re.compile(registration.regex) if isinstance(registration.regex, str) else registration.regex
        if pattern.search(text_value) is None:
            return False
    return True


def _text_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _validate_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
        raise ValueError(f"invalid plugin name: {name!r}")
    return name


def _validate_parse_error(value: str) -> None:
    if value not in {"ignore", "reply", "raise"}:
        raise ValueError("parse_error must be 'ignore', 'reply', or 'raise'")


def _looks_like_context(value: Any) -> bool:
    return hasattr(value, "plugin_name") and hasattr(value, "hook_bus")
