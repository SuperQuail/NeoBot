from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_chat.schema.types import ChatChunk, Message, ToolDefinition


class Provider(Protocol):
    """LLM Provider 接口：统一的 chat / stream / close 方法"""

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
        logger: Logger | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self._logger = logger or NullLogger()
        self._client: httpx.AsyncClient | None = None

    def _build_headers(self) -> dict[str, str]:
        """子类重写以提供特定的认证头"""
        return {"Content-Type": "application/json", **self.extra_headers}

    @staticmethod
    def _apply_payload_options(
        payload: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if extra_body:
            payload.update(extra_body)
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if top_p is not None:
            payload["top_p"] = top_p
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        return payload

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
