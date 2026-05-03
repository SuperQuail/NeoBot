from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_modloader.hooks import PluginHookBus, Rule

EventHandler = Callable[..., Any]
SubscriptionRecorder = Callable[[Any], None]


class PluginEventBus:
    def __init__(
        self,
        *,
        hook_bus: PluginHookBus,
        logger: Logger | None = None,
        record_subscription: SubscriptionRecorder | None = None,
    ) -> None:
        self._hook_bus = hook_bus
        self._logger = logger or NullLogger()
        self._record_subscription = record_subscription or (lambda _subscription: None)

    def message(
        self,
        *,
        group: bool = False,
        private: bool = False,
        sub_type: str | None = None,
        rule: Rule | None = None,
        priority: int = 0,
        timeout: float | None = None,
        block: bool = False,
        block_ai_reply: bool = False,
        regex: str | re.Pattern[str] | None = None,
        keywords: str | Sequence[str] | None = None,
        contains: str | Sequence[str] | None = None,
        not_contains: str | Sequence[str] | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
        if group and private:
            raise ValueError("group 和 private 不能同时为 True")
        message_type = "group" if group else "private" if private else None
        rule = _build_message_rule(
            rule=rule,
            regex=regex,
            keywords=keywords,
            contains=contains,
            not_contains=not_contains,
        )
        return self._decorator(
            post_type="message",
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            message_type=message_type,
            notice_type=None,
            request_type=None,
            meta_event_type=None,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
        )

    def notice(
        self,
        notice_type: str | None = None,
        *,
        sub_type: str | None = None,
        rule: Rule | None = None,
        priority: int = 0,
        timeout: float | None = None,
        block: bool = False,
        block_ai_reply: bool = False,
    ) -> Callable[[EventHandler], EventHandler]:
        return self._decorator(
            post_type="notice",
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            message_type=None,
            notice_type=notice_type,
            request_type=None,
            meta_event_type=None,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
        )

    def request(
        self,
        request_type: str | None = None,
        *,
        sub_type: str | None = None,
        rule: Rule | None = None,
        priority: int = 0,
        timeout: float | None = None,
        block: bool = False,
        block_ai_reply: bool = False,
    ) -> Callable[[EventHandler], EventHandler]:
        return self._decorator(
            post_type="request",
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            message_type=None,
            notice_type=None,
            request_type=request_type,
            meta_event_type=None,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
        )

    def meta_event(
        self,
        meta_event_type: str | None = None,
        *,
        sub_type: str | None = None,
        rule: Rule | None = None,
        priority: int = 0,
        timeout: float | None = None,
        block: bool = False,
        block_ai_reply: bool = False,
    ) -> Callable[[EventHandler], EventHandler]:
        return self._decorator(
            post_type="meta_event",
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            message_type=None,
            notice_type=None,
            request_type=None,
            meta_event_type=meta_event_type,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
        )

    def event(
        self,
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
    ) -> Callable[[EventHandler], EventHandler]:
        return self._decorator(
            post_type=post_type,
            timeout=timeout,
            block=block,
            block_ai_reply=block_ai_reply,
            message_type=message_type,
            notice_type=notice_type,
            request_type=request_type,
            meta_event_type=meta_event_type,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
        )

    def _decorator(
        self,
        *,
        post_type: str | None,
        timeout: float | None,
        block: bool,
        block_ai_reply: bool,
        message_type: str | None,
        notice_type: str | None,
        request_type: str | None,
        meta_event_type: str | None,
        sub_type: str | None,
        rule: Rule | None,
        priority: int,
    ) -> Callable[[EventHandler], EventHandler]:
        def register(handler: EventHandler) -> EventHandler:
            subscription = self._hook_bus.subscribe(
                handler,
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
                logger=self._logger,
            )
            self._record_subscription(subscription)
            return handler

        return register


def _build_message_rule(
    *,
    rule: Rule | None,
    regex: str | re.Pattern[str] | None,
    keywords: str | Sequence[str] | None,
    contains: str | Sequence[str] | None,
    not_contains: str | Sequence[str] | None,
) -> Rule | None:
    if regex is None and keywords is None and contains is None and not_contains is None:
        return rule

    keyword_values = _to_text_list(keywords)
    contains_values = _to_text_list(contains)
    not_contains_values = _to_text_list(not_contains)
    compiled_regex = re.compile(regex) if isinstance(regex, str) else regex

    async def combined(event: dict[str, Any]) -> bool:
        text = _message_text(event)
        if compiled_regex is not None and compiled_regex.search(text) is None:
            return False
        if keyword_values and not any(keyword in text for keyword in keyword_values):
            return False
        if contains_values and not all(value in text for value in contains_values):
            return False
        if not_contains_values and any(value in text for value in not_contains_values):
            return False
        if rule is None:
            return True
        result = rule(event)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    return combined


def _to_text_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _message_text(event: Any) -> str:
    data = _event_to_dict(event)
    raw_message = data.get("raw_message")
    if raw_message is not None:
        return str(raw_message)

    message = data.get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return "".join(_segment_text(segment) for segment in message)
    if message is None:
        return ""
    return str(message)


def _event_to_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="python")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _segment_text(segment: Any) -> str:
    if hasattr(segment, "model_dump"):
        segment = segment.model_dump(mode="python")
    if not isinstance(segment, dict):
        return str(segment)
    if segment.get("type") != "text":
        return ""
    data = segment.get("data")
    if isinstance(data, dict):
        return str(data.get("text", ""))
    return ""
