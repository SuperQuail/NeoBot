from __future__ import annotations

import httpx
import pytest

from neobot_chat.providers.deepseek_offical import DeepSeekOfficalProvider
from neobot_chat.providers.openai import OpenAIProvider
from neobot_chat.schema.exceptions import ProviderError

_OK_CHAT_BODY = {
    "choices": [{"message": {"role": "assistant", "content": "hi"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


def _openai_provider(handler) -> OpenAIProvider:
    provider = OpenAIProvider(api_key="test-key", model="test-model")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )
    return provider


@pytest.mark.asyncio
async def test_chat_retries_transport_error_then_succeeds():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=_OK_CHAT_BODY)

    provider = _openai_provider(handler)
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert message["content"] == "hi"
        assert len(calls) == 2
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_chat_does_not_retry_4xx():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = _openai_provider(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat([{"role": "user", "content": "hello"}])
        assert len(calls) == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_chat_retries_5xx_then_succeeds():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(200, json=_OK_CHAT_BODY)

    provider = _openai_provider(handler)
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert message["content"] == "hi"
        assert len(calls) == 2
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_deepseek_chat_raises_provider_error_after_retries_exhausted():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"error": {"message": "busy"}})

    provider = DeepSeekOfficalProvider(api_key="test-key", model="deepseek-chat")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )
    try:
        with pytest.raises(ProviderError, match="503"):
            await provider.chat([{"role": "user", "content": "hello"}])
        assert len(calls) == 3
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_stream_skips_non_json_lines_and_keeps_content():
    body = (
        "data: {\"choices\": [{\"delta\": {\"content\": \"he\"}}]}\n"
        "\n"
        "data: \n"
        ": keep-alive comment\n"
        "data: garbage-not-json\n"
        "data: null\n"
        "data: {\"choices\": [{\"delta\": {\"content\": \"llo\"}}]}\n"
        "data: [DONE]\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = _openai_provider(handler)
    try:
        deltas: list[str] = []
        final = None
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            if chunk.delta:
                deltas.append(chunk.delta)
            if chunk.message is not None:
                final = chunk.message
        assert deltas == ["he", "llo"]
        assert final is not None
        assert final["content"] == "hello"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_deepseek_stream_keeps_reasoning_and_content_on_bad_lines():
    body = (
        "data: {\"choices\": [{\"delta\": {\"reasoning_content\": \"think\"}}]}\n"
        "data: not-json-line\n"
        "data: {\"choices\": [{\"delta\": {\"content\": \"hi\"}}]}\n"
        "data: [DONE]\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = DeepSeekOfficalProvider(api_key="test-key", model="deepseek-reasoner")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )
    try:
        reasoning_deltas: list[str] = []
        deltas: list[str] = []
        final = None
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            if chunk.reasoning_delta:
                reasoning_deltas.append(chunk.reasoning_delta)
            if chunk.delta:
                deltas.append(chunk.delta)
            if chunk.message is not None:
                final = chunk.message
        assert reasoning_deltas == ["think"]
        assert deltas == ["hi"]
        assert final is not None
        assert final["content"] == "hi"
        assert final["extensions"]["deepseek"]["reasoning_content"] == "think"
    finally:
        await provider.close()


class _FakeStreamResponse:
    def __init__(self, lines: list[str], exc: BaseException | None = None) -> None:
        self._lines = lines
        self._exc = exc
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    async def __aenter__(self) -> _FakeStreamResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line
        if self._exc is not None:
            raise self._exc


class _StreamThatFailsOnEnter:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self) -> None:
        raise self._exc

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0
        self.is_closed = False

    def stream(self, method: str, url: str, **kwargs):
        self.calls += 1
        return self._responses.pop(0)

    async def aclose(self) -> None:
        self.is_closed = True


@pytest.mark.asyncio
async def test_stream_retries_transport_error_before_first_byte():
    client = _FakeClient(
        [
            _StreamThatFailsOnEnter(httpx.ConnectError("boom", request=None)),
            _FakeStreamResponse(["data: ok"]),
        ]
    )
    provider = OpenAIProvider(api_key="k", model="m")
    provider._client = client  # type: ignore[assignment]
    try:
        lines = [
            line
            async for line in provider._stream_with_retry(
                "POST", "/chat/completions", base_delay=0.01
            )
        ]
        assert lines == ["data: ok"]
        assert client.calls == 2
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_first_bytes_received():
    client = _FakeClient(
        [
            _FakeStreamResponse(
                ["data: first"], exc=httpx.ReadError("connection cut", request=None)
            )
        ]
    )
    provider = OpenAIProvider(api_key="k", model="m")
    provider._client = client  # type: ignore[assignment]
    try:
        collected: list[str] = []
        with pytest.raises(httpx.ReadError):
            async for line in provider._stream_with_retry(
                "POST", "/chat/completions", base_delay=0.01
            ):
                collected.append(line)
        assert collected == ["data: first"]
        assert client.calls == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_deepseek_4xx_error_body_mapped_into_provider_error():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "invalid api key"}})

    provider = DeepSeekOfficalProvider(api_key="bad", model="deepseek-chat")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.chat([{"role": "user", "content": "hello"}])
        assert "400" in str(exc_info.value)
        assert "invalid api key" in str(exc_info.value)
        assert len(calls) == 1
    finally:
        await provider.close()


class _FakeStreamErrorResponse:
    """带 4xx 状态码与错误 body 的假流式响应（check_status 阶段即失败）。"""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.is_error = True
        self.text = body

    async def __aenter__(self) -> _FakeStreamErrorResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_lines(self):
        yield "data: never"
        return


@pytest.mark.asyncio
async def test_deepseek_stream_4xx_raises_provider_error_without_retry():
    client = _FakeClient(
        [_FakeStreamErrorResponse(401, '{"error": {"message": "bad key"}}')]
    )
    provider = DeepSeekOfficalProvider(api_key="bad", model="deepseek-chat")
    provider._client = client  # type: ignore[assignment]
    try:
        with pytest.raises(ProviderError) as exc_info:
            async for _line in provider._stream_with_retry(
                "POST",
                "/chat/completions",
                check_status=provider._raise_for_status_with_body,
                base_delay=0.01,
            ):
                pass
        assert "401" in str(exc_info.value)
        assert "bad key" in str(exc_info.value)
        assert client.calls == 1
    finally:
        await provider.close()
