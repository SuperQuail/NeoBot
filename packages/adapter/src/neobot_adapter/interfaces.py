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

    @property
    def connected(self) -> bool: ...

    @property
    def http_url(self) -> str:
        """本地适配器（local 模式）的 HTTP 地址；不适用时为空串。"""
        ...

    @property
    def ws_url(self) -> str:
        """本地适配器（local 模式）的 WebSocket 地址；不适用时为空串。"""
        ...

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


@runtime_checkable
class AdapterReconfigurable(Protocol):
    """可在运行期改监听设置（host / port / access token）的适配器能力。

    只有「监听设置不固化在构造期」的适配器实现它（如 OneBotAdapter）；
    控制面用 ``isinstance(adapter, AdapterReconfigurable)`` 做能力查询，
    而不是 ``hasattr`` 猜测 —— 能力应当是接口的一部分，不是隐藏的可选成员。
    """

    @property
    def settings(self) -> Any:
        """当前解析后的监听设置（值对象，用于比较与展示）。"""
        ...

    def reconfigure(self, settings: Any) -> None:
        """写入新的监听设置；不触碰运行中的接收线程。"""
        ...
