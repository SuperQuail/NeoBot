"""Provider Port — LLM 聊天生成抽象"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """LLM Provider 协议，与 neobot_chat.providers.base.Provider 对齐"""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]: ...

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def close(self) -> None: ...
