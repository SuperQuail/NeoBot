from __future__ import annotations

from collections.abc import Awaitable, Callable

from neobot_chat.schema.types import State

StateNode = Callable[[State], Awaitable[State]]
StateCondition = Callable[[State], str]
