from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from neobot_chat.schema.types import ChatChunk, Message, ToolDefinition


class Provider(Protocol):
    """LLM Provider 协议：统一的 chat / stream / close 接口"""

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> Message: ...

    def stream(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[ChatChunk]: ...

    async def close(self) -> None: ...


class BaseHTTPProvider:
    """HTTP Provider 基类：管理 httpx 客户端生命周期"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self._client: httpx.AsyncClient | None = None

    def _build_headers(self) -> dict[str, str]:
        """子类重写以提供特定的认证头"""
        return {"Content-Type": "application/json", **self.extra_headers}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._build_headers(),
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
