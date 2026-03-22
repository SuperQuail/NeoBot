"""EventSource Port — 事件源抽象"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable


class Subscription(Protocol):
    """事件订阅句柄"""

    def unsubscribe(self) -> None: ...


@runtime_checkable
class EventSource(Protocol):
    """事件源协议，适配器实现此接口以提供事件流"""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], Awaitable[None] | None],
        **filters: Any,
    ) -> Subscription: ...
