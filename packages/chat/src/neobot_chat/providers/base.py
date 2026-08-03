from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_chat.schema.types import ChatChunk, Message, ToolDefinition

_RETRYABLE_HTTP_STATUSES = frozenset({500, 502, 503, 504})


def _is_transport_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


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

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 2,
        base_delay: float = 0.5,
        check_status: Callable[[httpx.Response], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """以指数退避重试传输错误与可重试的 5xx 状态码；

        4xx 及其他错误会立即抛出。"""
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = await self.client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(base_delay * (2**attempt))
                continue
            if (
                resp.status_code in _RETRYABLE_HTTP_STATUSES
                and attempt < max_retries
            ):
                await asyncio.sleep(base_delay * (2**attempt))
                continue
            if check_status is not None:
                await check_status(resp)
            else:
                resp.raise_for_status()
            return resp
        raise last_exc  # type: ignore[misc]

    async def _stream_with_retry(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 2,
        base_delay: float = 0.5,
        check_status: Callable[[httpx.Response], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """仅在响应体首个字节到达前重试；

        一旦流开始，错误将直接向上传播而不重试。"""
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            started = False
            try:
                async with self.client.stream(method, url, **kwargs) as resp:
                    if (
                        resp.status_code in _RETRYABLE_HTTP_STATUSES
                        and attempt < max_retries
                    ):
                        await asyncio.sleep(base_delay * (2**attempt))
                        continue
                    if check_status is not None:
                        await check_status(resp)
                    else:
                        resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        started = True
                        yield line
                    return
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if started:
                    raise
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(base_delay * (2**attempt))
        raise last_exc  # type: ignore[misc]

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
