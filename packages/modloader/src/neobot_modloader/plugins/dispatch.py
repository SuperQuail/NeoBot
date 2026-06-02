from __future__ import annotations

import inspect
import re
from collections.abc import Sequence
from typing import Any

from neobot_modloader.command_dsl import PatternError, PatternMatch
from neobot_modloader.message import Message
from neobot_modloader.reply import Reply
from neobot_modloader.plugins.registration import Handler, HandlerRegistration


def bind_handlers(plugin: Any, registrations: Sequence[HandlerRegistration], context: Any) -> None:
    for registration in registrations:
        # HookBus 负责事件筛选和超时/阻断；真正的参数注入留到 dispatch 阶段。
        subscription = context.hook_bus.subscribe(
            _wrap_handler(plugin, registration, context),
            post_type="message",
            message_type=_message_type_filter(registration),
            rule=_build_rule(registration),
            priority=registration.priority,
            timeout=registration.timeout,
            block=registration.block,
            block_ai_reply=registration.block_ai_reply,
            logger=context.logger,
        )
        context.record_subscription(subscription)


def _build_rule(registration: HandlerRegistration) -> Handler:
    async def rule(event: dict[str, Any]) -> bool:
        message = Message(event)
        if registration.kind == "command":
            # command 的 rule 只确认命令名命中，参数错误交给 handler 包装层回复/抛出。
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


def _wrap_handler(plugin: Any, registration: HandlerRegistration, context: Any) -> Handler:
    async def dispatch(event: dict[str, Any]) -> None:
        message = Message(event)
        match = registration.pattern.match(message)
        if not match.matched:
            await _handle_parse_error(registration, context, event, match)
            return
        await plugin._call_handler(registration.handler, context, event, message, match.values)

    return dispatch


async def _handle_parse_error(
    registration: HandlerRegistration,
    context: Any,
    event: dict[str, Any],
    match: PatternMatch,
) -> None:
    if registration.parse_error == "ignore":
        return
    if registration.parse_error == "raise":
        raise PatternError(match.error or "pattern parse failed")
    reply = Reply(context, event)
    await reply.send(f"参数错误，用法: {registration.pattern.usage}")


def _message_type_filter(registration: HandlerRegistration) -> str | None:
    if registration.group:
        return "group"
    if registration.private:
        return "private"
    return None


def _message_filters_match(registration: HandlerRegistration, event: dict[str, Any], message: Message) -> bool:
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
