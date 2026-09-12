from __future__ import annotations

from copy import deepcopy
import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest

from neobot_chat.models import RegisteredModel
from neobot_chat.providers.anthropic import AnthropicProvider
from neobot_chat.providers.deepseek_offical import DeepSeekOfficialProvider
from neobot_chat.providers.native_vision import NativeVisionFallbackProvider
from neobot_chat.providers.openai import OpenAIProvider
from neobot_chat.providers.vision import messages_have_images
from neobot_chat.schema.exceptions import NativeVisionUnsupportedError, ValidationError
from neobot_chat.schema.types import ChatChunk

DATA_URL = "data:image/png;base64,aW1hZ2U="
MESSAGES = [{"role": "user", "content": [
    {"type": "text", "text": "What is shown?"},
    {"type": "image_url", "image_url": {"url": DATA_URL}},
]}]
OK_BODY = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
PROVIDERS = [OpenAIProvider, DeepSeekOfficialProvider, AnthropicProvider]


def with_transport(provider_class, handler, *, native_vision=True):
    provider = provider_class(api_key="test", model="vision-model", native_vision=native_vision)
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.test"
    )
    return provider


class TextProvider:
    native_vision = False
    model = "text-model"

    def __init__(self):
        self.calls = []
        self.closed = False

    async def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        return {"role": "assistant", "content": "text reply", "extensions": {"usage": {"input_tokens": 7}}}

    async def stream(self, messages, tools=None):
        yield ChatChunk(delta="text reply")
        yield ChatChunk(message=await self.chat(messages, tools))

    async def close(self):
        self.closed = True


@pytest.mark.parametrize("provider_class", PROVIDERS)
@pytest.mark.parametrize("url", [DATA_URL, "https://example.test/image.png"])
async def test_chat_preserves_images_in_each_wire_format(provider_class, url):
    payloads = []
    messages = deepcopy(MESSAGES)
    messages[0]["content"][1]["image_url"]["url"] = url
    original = deepcopy(messages)

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]} if provider_class is AnthropicProvider else OK_BODY)

    provider = with_transport(provider_class, handler)
    try:
        assert provider.native_vision
        await provider.chat(messages)
        blocks = payloads[0]["messages"][0]["content"]
        assert blocks[0]["text"] == "What is shown?"
        if provider_class is AnthropicProvider:
            assert blocks[1]["type"] == "image"
            assert blocks[1]["source"] == (
                {"type": "base64", "media_type": "image/png", "data": "aW1hZ2U="}
                if url == DATA_URL else {"type": "url", "url": url}
            )
        else:
            assert blocks[1]["image_url"]["url"] == url
        assert messages == original
    finally:
        await provider.close()


@pytest.mark.parametrize("provider_class", PROVIDERS)
@pytest.mark.parametrize("stream", [False, True])
async def test_explicit_image_rejection_downgrades_once_with_notice(provider_class, stream):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "This model does not support image"}})

    primary = with_transport(provider_class, handler)
    fallback, logger = TextProvider(), Mock()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=logger)
    original = deepcopy(MESSAGES)
    tools = [{"type": "function", "function": {"name": name, "parameters": {}}} for name in ["image_context__add_image", "other__tool"]]
    try:
        if stream:
            chunks = [chunk async for chunk in provider.stream(MESSAGES, tools)]
            response = chunks[-1].message
            assert chunks[0].delta == "text reply"
        else:
            response = await provider.chat(MESSAGES, tools)
        assert not provider.native_vision
        assert provider.model == "text-model"
        assert response["extensions"]["native_vision_fallback"]["reason"].startswith("HTTP 400")
        assert response["extensions"]["usage"]["input_tokens"] == 7
        await provider.chat(MESSAGES, tools)
        assert len(requests) == 1
        assert len(fallback.calls) == 2
        for messages, sent_tools in fallback.calls:
            assert not messages_have_images(messages)
            assert messages[0]["role"] == "system"
            assert "不能声称" in messages[0]["content"]
            assert "What is shown?" in messages[1]["content"]
            assert "图片未发送" in messages[1]["content"]
            assert DATA_URL not in str(messages)
            assert [t["function"]["name"] for t in sent_tools] == ["other__tool"]
        assert MESSAGES == original
        logger.error.assert_called_once()
        assert DATA_URL not in str(logger.error.call_args)
    finally:
        await provider.close()
    assert fallback.closed
    assert primary._client.is_closed




class VisionProvider(TextProvider):
    native_vision = True
    model = "vision-model"


@pytest.mark.parametrize("stream", [False, True])
async def test_vision_capable_fallback_keeps_images_and_tools(stream):
    """视觉模型作为回退时：图片原样转发、工具不过滤、能力保持可用。"""
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "This model does not support image"}})

    primary = with_transport(OpenAIProvider, handler)
    fallback = VisionProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    tools = [{"type": "function", "function": {"name": name, "parameters": {}}} for name in ["image_context__add_image", "other__tool"]]
    original = deepcopy(MESSAGES)
    try:
        if stream:
            response = [chunk async for chunk in provider.stream(MESSAGES, tools)][-1].message
        else:
            response = await provider.chat(MESSAGES, tools)
        assert provider.native_vision is True
        assert provider.model == "vision-model"
        notice = response["extensions"]["native_vision_fallback"]
        assert notice["to_model"] == "fallback"
        assert "视觉模型" in notice["notice"]
        sent_messages, sent_tools = fallback.calls[0]
        assert messages_have_images(sent_messages)
        assert DATA_URL in str(sent_messages)
        assert [t["function"]["name"] for t in sent_tools] == ["image_context__add_image", "other__tool"]
        assert MESSAGES == original
    finally:
        await provider.close()


def test_strip_images_with_vision_fallback_is_rejected():
    """显式要求剥离图片时，视觉回退属于配置矛盾，必须报错。"""
    primary = with_transport(OpenAIProvider, lambda request: httpx.Response(200, json=OK_BODY))
    with pytest.raises(ValidationError):
        NativeVisionFallbackProvider(primary, VisionProvider(), logger=Mock(), strip_images=True)

@pytest.mark.parametrize("provider_class", PROVIDERS)
@pytest.mark.parametrize("status,body", [
    (400, "Invalid image URL"), (400, "Image exceeds size limit"),
    (400, "Invalid tools schema"), (401, "This model does not support image"),
    (429, "This model does not support image"), (503, "This model does not support image"),
])
async def test_other_http_failures_never_downgrade(provider_class, status, body, monkeypatch):
    async def no_sleep(_):
        pass
    monkeypatch.setattr("neobot_chat.providers.base.asyncio.sleep", no_sleep)
    primary = with_transport(provider_class, lambda request: httpx.Response(status, json={"error": {"message": body}}))
    fallback, logger = TextProvider(), Mock()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=logger)
    try:
        with pytest.raises(Exception) as error:
            await provider.chat(MESSAGES)
        assert not isinstance(error.value, NativeVisionUnsupportedError)
        assert provider.native_vision
        assert fallback.calls == []
        logger.error.assert_not_called()
    finally:
        await provider.close()


async def test_transport_failure_never_downgrades(monkeypatch):
    async def no_sleep(_):
        pass
    monkeypatch.setattr("neobot_chat.providers.base.asyncio.sleep", no_sleep)

    def handler(request):
        raise httpx.ConnectError("connection lost", request=request)

    primary = with_transport(OpenAIProvider, handler)
    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    try:
        with pytest.raises(httpx.ConnectError):
            await provider.chat(MESSAGES)
        assert provider.native_vision
        assert fallback.calls == []
    finally:
        await provider.close()


async def test_image_rejection_without_images_does_not_downgrade():
    primary = with_transport(OpenAIProvider, lambda request: httpx.Response(400, text="This model does not support image"))
    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    try:
        with pytest.raises(NativeVisionUnsupportedError):
            await provider.chat([{"role": "user", "content": "text only"}])
        assert provider.native_vision
        assert fallback.calls == []
    finally:
        await provider.close()


async def test_deepseek_non_user_image_is_not_sent_or_silently_lost():
    handler = Mock()
    primary = with_transport(DeepSeekOfficialProvider, handler)
    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    try:
        messages = [{**MESSAGES[0], "role": "assistant"}]
        response = await provider.chat(messages)
        assert "only accepts images in user" in response["extensions"]["native_vision_fallback"]["reason"]
        assert not messages_have_images(fallback.calls[0][0])
        handler.assert_not_called()
    finally:
        await provider.close()


def test_anthropic_tool_result_and_assistant_image_conversion():
    provider = AnthropicProvider(api_key="test", model="claude", native_vision=True)
    system, messages = provider._convert_messages([
        {"role": "system", "content": [{"type": "text", "text": "system"}]},
        {"role": "tool", "tool_call_id": "call-1", "content": MESSAGES[0]["content"]},
        {**MESSAGES[0], "role": "assistant"},
    ])
    assert system == "system"
    assert messages[0]["content"][0]["content"][1]["source"]["data"] == "aW1hZ2U="
    assert messages[1]["content"][1]["source"]["data"] == "aW1hZ2U="
    with pytest.raises(NativeVisionUnsupportedError):
        provider._convert_messages([{**MESSAGES[0], "role": "system"}])


@pytest.mark.parametrize("provider_class", [OpenAIProvider, DeepSeekOfficialProvider])
def test_openai_compatible_converts_anthropic_images_without_leaking_extensions(provider_class):
    provider = provider_class(api_key="test", model="vision", native_vision=True)
    payload = provider._build_payload([
        {"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aW1hZ2U="}},
        ], "extensions": {"native_vision_fallback": {"notice": "local only"}}},
    ], None, stream=False)
    message = payload["messages"][0]
    assert message["content"][0]["image_url"]["url"] == DATA_URL
    assert "extensions" not in message


def test_anthropic_single_assistant_image_is_not_dropped():
    provider = AnthropicProvider(api_key="test", model="vision", native_vision=True)
    _, converted = provider._convert_messages([
        {"role": "assistant", "content": {"type": "image_url", "image_url": {"url": DATA_URL}}},
    ])
    assert converted[0]["content"][0]["source"]["data"] == "aW1hZ2U="


def test_anthropic_invalid_data_url_is_validation_not_capability_failure():
    provider = AnthropicProvider(api_key="test", model="claude", native_vision=True)
    with pytest.raises(ValidationError):
        provider._convert_messages([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png,not-base64"}}]}])


@pytest.mark.parametrize("provider_name,provider_class", [("OpenAI", OpenAIProvider), ("DeepSeek", DeepSeekOfficialProvider), ("Anthropic", AnthropicProvider)])
@pytest.mark.parametrize("enabled", [False, True])
def test_registration_propagates_capability(provider_name, provider_class, enabled):
    registered = RegisteredModel(name="main", description="test", provider_name=provider_name,
                                 model_name="model", base_url="https://example.test", api_key="key", native_vision=enabled)
    provider = registered.create_provider()
    assert isinstance(provider, provider_class)
    assert provider.native_vision is enabled


async def test_stream_never_replays_after_partial_output():
    class PartialProvider(TextProvider):
        native_vision = True

        async def stream(self, messages, tools=None):
            yield ChatChunk(delta="partial")
            raise NativeVisionUnsupportedError("model does not support image")

    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(PartialProvider(), fallback, logger=Mock())
    stream = provider.stream(MESSAGES)
    assert (await anext(stream)).delta == "partial"
    with pytest.raises(NativeVisionUnsupportedError):
        await anext(stream)
    assert fallback.calls == []
    assert provider.native_vision
    await provider.close()


@pytest.mark.parametrize("stream", [False, True])
async def test_concurrent_vision_rejections_both_retry_text_route(stream):
    class ConcurrentPrimary(TextProvider):
        native_vision = True

        def __init__(self):
            super().__init__()
            self.arrived = 0
            self.ready = asyncio.Event()

        async def chat(self, messages, tools=None):
            self.arrived += 1
            if self.arrived == 2:
                self.ready.set()
            await self.ready.wait()
            raise NativeVisionUnsupportedError("model does not support image")

        async def stream(self, messages, tools=None):
            yield ChatChunk(message=await self.chat(messages, tools))

    primary, fallback, logger = ConcurrentPrimary(), TextProvider(), Mock()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=logger)

    async def invoke():
        if stream:
            return [chunk async for chunk in provider.stream(MESSAGES)][-1].message
        return await provider.chat(MESSAGES)

    results = await asyncio.gather(invoke(), invoke())
    assert all(response["extensions"]["native_vision_fallback"] for response in results)
    assert len(fallback.calls) == 2
    assert not provider.native_vision
    logger.error.assert_called_once()
    await provider.close()


@pytest.mark.parametrize("body", [
    "'image_url' is not supported for this model",
    "Invalid type for 'messages[0].content': expected a string, but got an array instead",
    "Image inputs are not supported",
])
async def test_compatible_api_capability_error_forms(body):
    primary = with_transport(OpenAIProvider, lambda request: httpx.Response(422, text=body))
    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    try:
        await provider.chat(MESSAGES)
        assert not provider.native_vision
        assert len(fallback.calls) == 1
    finally:
        await provider.close()


def test_wrapper_proxies_effective_max_tokens():
    """包装器必须如实上报当前生效路由的输出上限。

    不代理时编排器读到 None，「这一轮被输出上限截断」在开启原生视觉的主模型上
    完全无法观测 —— 而截断正是丢回复的主因。
    """
    primary = TextProvider()
    primary.max_tokens = 200000
    fallback = TextProvider()
    fallback.max_tokens = 4096

    healthy = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    assert healthy.max_tokens == 200000
    assert healthy.model == "text-model"

    degraded = NativeVisionFallbackProvider(
        primary, fallback, logger=Mock(),
        startup_reason="启动期不可用", strip_images=False,
    )
    assert degraded.max_tokens == 4096


def test_wrapper_max_tokens_assignment_is_ignored_not_crashing():
    """对包装器赋值 max_tokens 不得崩溃，也不得改写被代理的共享 provider 预算。

    线上事故：self-heal / 解题 agent 用 `provider.max_tokens = cfg.max_tokens` 覆盖预算，
    包装器一旦变成只读属性，启动即 AttributeError；而真的写下去又会把主回复模型的预算
    一起压到 8192 一类的小值（那正是丢回复的根因），所以只告警、不改写。
    """
    primary = TextProvider()
    primary.max_tokens = 200000
    fallback = TextProvider()
    fallback.max_tokens = 4096
    logger = Mock()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=logger)

    provider.max_tokens = 8192

    assert provider.max_tokens == 200000
    assert primary.max_tokens == 200000
    assert fallback.max_tokens == 4096
    assert logger.warning.called


def test_wrapper_max_tokens_is_none_when_route_has_no_budget():
    """底层没声明上限时如实返回 None，不要凭空编造数字。"""
    provider = NativeVisionFallbackProvider(TextProvider(), TextProvider(), logger=Mock())

    assert provider.max_tokens is None


async def test_unrelated_array_schema_error_does_not_degrade():
    primary = with_transport(OpenAIProvider, lambda request: httpx.Response(400, text="Invalid type for tools: expected a string, but got an array instead"))
    fallback = TextProvider()
    provider = NativeVisionFallbackProvider(primary, fallback, logger=Mock())
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat(MESSAGES)
        assert provider.native_vision
        assert fallback.calls == []
    finally:
        await provider.close()
