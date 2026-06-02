from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef

from neobot_adapter.eventing import EventHandlerFunc, Subscription
from neobot_adapter.model.response import SendMsgResponse


@runtime_checkable
class CoreLike(Protocol):
    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None: ...

    def call_api_sync(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None: ...


@runtime_checkable
class RuntimeAdapter(Protocol):
    @property
    def requires_connection_wait(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def wait_for_connection(self, timeout: float | None = None) -> bool: ...

    def subscribe(
        self,
        event_type: Any,
        handler: EventHandlerFunc,
        **filters: Any,
    ) -> Subscription: ...

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
    ) -> dict[str, Any] | None: ...

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
    ) -> SendMsgResponse: ...
