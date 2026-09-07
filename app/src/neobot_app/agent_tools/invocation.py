"""Host-only bridge between existing skill routing and the shared tool runtime."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .contracts import ToolContext


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    context: ToolContext
    dispatch: Callable[[str, dict], Awaitable[Any]] | None = None
    definitions: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)


CURRENT_INVOCATION: ContextVar[ToolInvocation | None] = ContextVar("agent_tool_invocation", default=None)
CURRENT_HUMAN_MESSAGE: ContextVar[bool] = ContextVar("agent_tools_human_message", default=False)


def human_message_entry(method: Callable) -> Callable:
    """Mark only parsed adapter message entrypoints, never tool arguments or notices."""
    @wraps(method)
    async def wrapped(self: Any, event: dict, *args: Any, **kwargs: Any) -> Any:
        human = (isinstance(event, dict) and event.get("post_type") == "message"
                 and event.get("message_type") in {"group", "private"}
                 and str(event.get("user_id", "")) != str(event.get("self_id", "")))
        marker = CURRENT_HUMAN_MESSAGE.set(human)
        try:
            return await method(self, event, *args, **kwargs)
        finally:
            CURRENT_HUMAN_MESSAGE.reset(marker)
    return wrapped
