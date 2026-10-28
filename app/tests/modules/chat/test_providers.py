from __future__ import annotations

import json

import httpx
import pytest

from neobot_chat.models import ModelSettings, RegisteredModel
from neobot_chat.providers.anthropic import AnthropicProvider
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
@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
@pytest.mark.parametrize(
    "tool_fields",
    [{}, {"tool_calls": None}, {"tool_calls": []}],
    ids=["missing", "null", "empty"],
)
async def test_chat_accepts_no_tool_calls(provider_cls, tool_fields):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": "done", **tool_fields,
            }}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        })

    provider = provider_cls(api_key="test-key", model="test-model")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert message["role"] == "assistant"
        assert message["content"] == "done"
        assert "tool_calls" not in message
        assert message["extensions"]["usage"]["input_tokens"] == 3
        assert message["extensions"]["usage"]["output_tokens"] == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
@pytest.mark.parametrize(
    "tool_fields",
    [{}, {"tool_calls": None}, {"tool_calls": []}],
    ids=["missing", "null", "empty"],
)
@pytest.mark.parametrize("with_tool_call", [False, True])
async def test_stream_accepts_no_tool_calls_in_delta(
    provider_cls, tool_fields, with_tool_call,
):
    tool_call = {
        "id": "call-1", "type": "function",
        "function": {"name": "read_archive", "arguments": "{}"},
    }
    deltas = [{"content": "do", **tool_fields}]
    if with_tool_call:
        deltas.append({"tool_calls": [{"index": 0, **tool_call}]})
    deltas.append({"content": "ne", **tool_fields})
    body = "".join(
        "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\n"
        for delta in deltas
    ) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = provider_cls(api_key="test-key", model="test-model")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        chunks = [
            chunk async for chunk in provider.stream(
                [{"role": "user", "content": "hello"}],
            )
        ]
        assert "".join(chunk.delta or "" for chunk in chunks) == "done"
        message = chunks[-1].message
        assert message is not None
        assert message["content"] == "done"
        if with_tool_call:
            assert message["tool_calls"] == [tool_call]
        else:
            assert "tool_calls" not in message
    finally:
        await provider.close()


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


# ── finish_reason 透出 ──────────────────────────────────────────
# 编排器只能靠这个字段区分「模型主动沉默」与「输出被长度上限截断」；
# provider 一旦丢掉它，空输出就变成了不可观测的静默丢回复。


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
async def test_chat_surfaces_finish_reason(provider_cls):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "length",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10000},
        })

    provider = provider_cls(api_key="k", model="m")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert message["extensions"]["finish_reason"] == "length"
        assert message["extensions"]["usage"]["output_tokens"] == 10000
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
async def test_chat_omits_finish_reason_when_absent(provider_cls):
    """缺失/空值不得写入空字符串这种伪信号。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": ""}],
        })

    provider = provider_cls(api_key="k", model="m")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert "finish_reason" not in (message.get("extensions") or {})
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
async def test_stream_surfaces_finish_reason(provider_cls):
    body = (
        'data: {"choices": [{"delta": {"content": "hi"}, "finish_reason": null}]}\n'
        'data: {"choices": [{"delta": {}, "finish_reason": "length"}]}\n'
        "data: [DONE]\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "text/event-stream"},
        )

    provider = provider_cls(api_key="k", model="m")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        final = None
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            if chunk.message is not None:
                final = chunk.message
        assert final is not None
        assert final["extensions"]["finish_reason"] == "length"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_anthropic_chat_maps_max_tokens_to_length():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": ""}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 5, "output_tokens": 4096},
        })

    provider = AnthropicProvider(api_key="k", model="claude")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        message = await provider.chat([{"role": "user", "content": "hello"}])
        assert message["extensions"]["finish_reason"] == "length"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_anthropic_stream_surfaces_stop_reason_from_message_delta():
    body = (
        "event: content_block_delta\n"
        'data: {"delta": {"type": "text_delta", "text": "hi"}}\n'
        "event: message_delta\n"
        'data: {"delta": {"stop_reason": "max_tokens"}}\n'
        "event: message_stop\n"
        'data: {"type": "message_stop"}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "text/event-stream"},
        )

    provider = AnthropicProvider(api_key="k", model="claude")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        final = None
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            if chunk.message is not None:
                final = chunk.message
        assert final is not None
        assert final["extensions"]["finish_reason"] == "length"
    finally:
        await provider.close()


# ── 顶层推理强度下发 ──────────────────────────────────────────
# 配置层解析好的 reasoning_effort 必须原样进请求体：OpenAI 系写 reasoning_effort，
# Claude 系写 output_config.effort；显式顶层值优先于 extra_body / 旧 DeepSeek 私有键。

_ANTHROPIC_OK_BODY = {
    "content": [{"type": "text", "text": "hi"}],
    "stop_reason": "end_turn",
}


async def _captured_chat_payload(provider, response_json: dict) -> dict:
    """跑一次 chat，返回 MockTransport 捕获到的请求体。"""
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_json)

    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        await provider.chat([{"role": "user", "content": "hi"}])
    finally:
        await provider.close()
    assert len(captured) == 1
    return captured[0]


@pytest.mark.asyncio
async def test_openai_provider_dispatches_effort_in_openai_format():
    payload = await _captured_chat_payload(
        OpenAIProvider(api_key="k", model="m", reasoning_effort="high"), _OK_CHAT_BODY,
    )
    assert payload["reasoning_effort"] == "high"
    assert "output_config" not in payload


@pytest.mark.asyncio
async def test_openai_provider_dispatches_claude_format_merging_output_config():
    payload = await _captured_chat_payload(
        OpenAIProvider(
            api_key="k",
            model="m",
            reasoning_effort="high",
            reasoning_effort_format="claude",
            extra_body={"output_config": {"format": "json"}},
        ),
        _OK_CHAT_BODY,
    )
    # 只写 effort，不能整体覆盖调用方已有的 output_config 其它键
    assert payload["output_config"] == {"format": "json", "effort": "high"}
    assert "reasoning_effort" not in payload


@pytest.mark.asyncio
async def test_openai_provider_top_level_effort_wins_over_extra_body():
    payload = await _captured_chat_payload(
        OpenAIProvider(
            api_key="k",
            model="m",
            reasoning_effort="max",
            extra_body={"reasoning_effort": "low"},
        ),
        _OK_CHAT_BODY,
    )
    assert payload["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_openai_provider_omits_empty_effort():
    payload = await _captured_chat_payload(OpenAIProvider(api_key="k", model="m"), _OK_CHAT_BODY)
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload


@pytest.mark.asyncio
async def test_anthropic_provider_writes_output_config_effort_for_openai_format():
    """Anthropic Messages API 只认 output_config.effort：配置格式是 openai 也照旧写这里。"""
    payload = await _captured_chat_payload(
        AnthropicProvider(
            api_key="k",
            model="claude",
            reasoning_effort="max",
            reasoning_effort_format="openai",
            extra_body={"output_config": {"format": "json"}},
        ),
        _ANTHROPIC_OK_BODY,
    )
    assert payload["output_config"] == {"format": "json", "effort": "max"}
    assert "reasoning_effort" not in payload


@pytest.mark.asyncio
async def test_anthropic_stream_payload_carries_output_config_effort():
    captured: list[dict] = []
    body = (
        "event: content_block_delta\n"
        'data: {"delta": {"type": "text_delta", "text": "hi"}}\n'
        "event: message_stop\n"
        'data: {"type": "message_stop"}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "text/event-stream"},
        )

    provider = AnthropicProvider(api_key="k", model="claude", reasoning_effort="high")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com",
    )
    try:
        async for _chunk in provider.stream([{"role": "user", "content": "hi"}]):
            pass
    finally:
        await provider.close()

    assert len(captured) == 1
    assert captured[0]["output_config"] == {"effort": "high"}
    assert "reasoning_effort" not in captured[0]


@pytest.mark.asyncio
async def test_anthropic_provider_omits_empty_effort():
    payload = await _captured_chat_payload(
        AnthropicProvider(api_key="k", model="claude"), _ANTHROPIC_OK_BODY,
    )
    assert "output_config" not in payload


@pytest.mark.asyncio
async def test_deepseek_top_level_effort_overrides_legacy_private_key():
    payload = await _captured_chat_payload(
        DeepSeekOfficalProvider(
            api_key="k",
            model="deepseek-chat",
            reasoning_effort="max",
            extra_body={
                "__deepseek_thinking_mode__": "true",
                "__deepseek_reasoning_effort__": "high",
            },
        ),
        _OK_CHAT_BODY,
    )
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_deepseek_legacy_private_key_still_dispatches_without_top_level():
    payload = await _captured_chat_payload(
        DeepSeekOfficalProvider(
            api_key="k",
            model="deepseek-chat",
            extra_body={
                "__deepseek_thinking_mode__": "true",
                "__deepseek_reasoning_effort__": "high",
            },
        ),
        _OK_CHAT_BODY,
    )
    assert payload["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_deepseek_thinking_disabled_never_sends_effort():
    payload = await _captured_chat_payload(
        DeepSeekOfficalProvider(
            api_key="k",
            model="deepseek-chat",
            reasoning_effort="max",
            extra_body={"__deepseek_thinking_mode__": "false"},
        ),
        _OK_CHAT_BODY,
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in payload


@pytest.mark.asyncio
async def test_deepseek_ignores_claude_format_effort():
    """DeepSeek /chat/completions 没有 output_config：即使调用方误传 claude 格式也不能照发。"""
    payload = await _captured_chat_payload(
        DeepSeekOfficalProvider(
            api_key="k",
            model="deepseek-chat",
            reasoning_effort="high",
            reasoning_effort_format="claude",
            extra_body={"__deepseek_thinking_mode__": "true"},
        ),
        _OK_CHAT_BODY,
    )
    assert "output_config" not in payload
    assert "reasoning_effort" not in payload


@pytest.mark.asyncio
async def test_anthropic_top_level_effort_drops_conflicting_extra_body_key():
    """显式 Claude 系强度必须完全胜出：extra_body 里的 reasoning_effort 要清掉。"""
    payload = await _captured_chat_payload(
        AnthropicProvider(
            api_key="k",
            model="claude",
            reasoning_effort="max",
            extra_body={"reasoning_effort": "low"},
        ),
        _ANTHROPIC_OK_BODY,
    )
    assert payload["output_config"] == {"effort": "max"}
    assert "reasoning_effort" not in payload


@pytest.mark.asyncio
async def test_openai_top_level_effort_drops_conflicting_output_config_effort():
    """反向同理：显式 OpenAI 系强度时，extra_body 里残留的 output_config.effort 不能跟着发。"""
    payload = await _captured_chat_payload(
        OpenAIProvider(
            api_key="k",
            model="m",
            reasoning_effort="max",
            extra_body={"output_config": {"format": "json", "effort": "low"}},
        ),
        _OK_CHAT_BODY,
    )
    assert payload["reasoning_effort"] == "max"
    assert payload["output_config"] == {"format": "json"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("none", "high"),
        ("minimal", "high"),
        ("low", "high"),
        ("medium", "high"),
        ("xhigh", "max"),
        ("high", "high"),
        ("max", "max"),
    ],
)
async def test_deepseek_normalizes_top_level_effort_to_high_or_max(configured, expected):
    payload = await _captured_chat_payload(
        DeepSeekOfficalProvider(
            api_key="k",
            model="deepseek-chat",
            reasoning_effort=configured,
            extra_body={"__deepseek_thinking_mode__": "true"},
        ),
        _OK_CHAT_BODY,
    )
    assert payload["reasoning_effort"] == expected


def test_registered_model_forwards_reasoning_effort_to_every_provider():
    """配置层解析好的两个字段必须一路透传到三家 provider。"""
    settings = ModelSettings(reasoning_effort="xhigh", reasoning_effort_format="claude")
    cases = (
        ("OpenAI", OpenAIProvider),
        ("Anthropic", AnthropicProvider),
        ("DeepSeek", DeepSeekOfficalProvider),
    )
    for provider_name, expected_cls in cases:
        model = RegisteredModel(
            model_ref="m",
            display_name="m",
            provider_name=provider_name,
            model_name="test-model",
            base_url="https://example.com",
            api_key="k",
            settings=settings,
        )
        provider = model._build_provider()
        assert isinstance(provider, expected_cls), provider_name
        assert provider.reasoning_effort == "xhigh", provider_name
        assert provider.reasoning_effort_format == "claude", provider_name
