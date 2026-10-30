"""可组合消息规则；短路执行，兼容已有同步或异步 rule 回调。"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from neobot_modloader.message import Message


class Rule:
    def __init__(self, predicate: Callable[[Mapping[str, Any]], Any]) -> None:
        self.predicate = predicate

    async def __call__(self, event: Mapping[str, Any]) -> bool:
        result = self.predicate(event)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def __and__(self, other: Rule) -> Rule:
        async def both(event):
            return await self(event) and await other(event)

        return Rule(both)

    def __or__(self, other: Rule) -> Rule:
        async def either(event):
            return await self(event) or await other(event)

        return Rule(either)

    def __invert__(self) -> Rule:
        async def inverse(event):
            return not await self(event)

        return Rule(inverse)


def starts_with(prefix: str) -> Rule:
    return Rule(lambda event: Message(event).text.lstrip().startswith(prefix))


def mentioned() -> Rule:
    """仅匹配协议中明确 @ 当前机器人的消息，不把昵称文字当成身份。"""

    def matches(event):
        self_id = event.get("self_id")
        return self_id is not None and any(segment.qq == str(self_id) for segment in Message(event).ats)

    return Rule(matches)


def has_segment(kind: str) -> Rule:
    return Rule(lambda event: bool(Message(event).of_type(kind)))
