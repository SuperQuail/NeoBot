"""工具参数管线回归：空/损坏 arguments 不得让会话永久失败。

根因（见 dev-test/review/findings/R2.md P1）：Anthropic 流式下无参工具
（content_block_start 带 input:{} 且没有 input_json_delta）会留下空串
arguments，回灌历史时 json.loads("") 在发出任何 HTTP 请求前抛
JSONDecodeError，坏消息永久留在 messages 里。
"""
from __future__ import annotations

import json

import httpx
import pytest

from neobot_chat.providers.anthropic import AnthropicProvider
from neobot_chat.providers.base import (
    normalized_tool_calls,
    tool_arguments_object,
    tool_arguments_text,
)
from neobot_chat.providers.deepseek_offical import DeepSeekOfficalProvider
from neobot_chat.providers.openai import OpenAIProvider


class _RecordingLogger:
    """收集 warning，用来区分「本来无参数」与「参数损坏被修复」。"""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def bind(self, **ctx):
        return self

    def debug(self, msg: str, **kw) -> None:
        return None

    def info(self, msg: str, **kw) -> None:
        return None

    def warning(self, msg: str, **kw) -> None:
        self.warnings.append((msg, kw))

    def error(self, msg: str, **kw) -> None:
        return None

    def exception(self, msg: str, **kw) -> None:
        return None


def _provider_with_sse(cls, body: str, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "text/event-stream"}
        )

    provider = cls(api_key="k", model="m", **kwargs)
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com"
    )
    return provider


def _anthropic_no_argument_tool_sse() -> str:
    """Anthropic 官方协议：input 为空对象时没有 input_json_delta。"""
    return (
        "event: message_start\n"
        'data: {"type": "message_start", "message": {"id": "msg_1"}}\n'
        "event: content_block_start\n"
        'data: {"type": "content_block_start", "index": 0, "content_block": '
        '{"type": "tool_use", "id": "toolu_1", "name": "list_agents", "input": {}}}\n'
        "event: content_block_stop\n"
        'data: {"type": "content_block_stop", "index": 0}\n'
        "event: message_delta\n"
        'data: {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}\n'
        "event: message_stop\n"
        'data: {"type": "message_stop"}\n'
    )


def _anthropic_tool_sse(deltas: list[str], initial_input: object = None) -> str:
    start_block: dict = {"type": "tool_use", "id": "toolu_1", "name": "f"}
    if initial_input is not None:
        start_block["input"] = initial_input
    lines = [
        "event: content_block_start\n"
        "data: " + json.dumps({"type": "content_block_start", "index": 0, "content_block": start_block}) + "\n"
    ]
    for piece in deltas:
        lines.append(
            "event: content_block_delta\n"
            "data: "
            + json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": piece},
                }
            )
            + "\n"
        )
    lines.append(
        "event: content_block_stop\n"
        'data: {"type": "content_block_stop", "index": 0}\n'
        "event: message_stop\n"
        'data: {"type": "message_stop"}\n'
    )
    return "".join(lines)


async def _final_message(provider) -> dict:
    final = None
    async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
        if chunk.message is not None:
            final = chunk.message
    assert final is not None
    return final


# ── Anthropic：无参工具 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_stream_no_argument_tool_arguments_are_valid_json():
    provider = _provider_with_sse(AnthropicProvider, _anthropic_no_argument_tool_sse())
    try:
        message = await _final_message(provider)
    finally:
        await provider.close()
    tool_call = message["tool_calls"][0]
    assert tool_call["function"]["arguments"] == "{}"
    assert json.loads(tool_call["function"]["arguments"]) == {}


@pytest.mark.asyncio
async def test_anthropic_stream_no_argument_tool_message_can_be_replayed():
    """流式产出 -> 回灌历史：旧代码在这里抛 JSONDecodeError。"""
    provider = _provider_with_sse(AnthropicProvider, _anthropic_no_argument_tool_sse())
    try:
        message = await _final_message(provider)
        _, converted = provider._convert_messages(
            [
                {"role": "user", "content": "hi"},
                message,
                {"role": "tool", "tool_call_id": "toolu_1", "content": "ok"},
            ]
        )
    finally:
        await provider.close()
    tool_use = converted[1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["input"] == {}


@pytest.mark.asyncio
async def test_anthropic_stream_input_json_deltas_are_not_concatenated_with_initial_input():
    """有增量时，增量是权威值：绝不能被初始 input 播种后拼接成非法 JSON。"""
    body = _anthropic_tool_sse(['{"loc', 'ation": "SF"}'], initial_input={})
    provider = _provider_with_sse(AnthropicProvider, body)
    try:
        message = await _final_message(provider)
    finally:
        await provider.close()
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"location": "SF"}


@pytest.mark.asyncio
async def test_anthropic_stream_deltas_win_over_non_empty_initial_input():
    body = _anthropic_tool_sse(['{"a": 1}'], initial_input={"stale": True})
    provider = _provider_with_sse(AnthropicProvider, body)
    try:
        message = await _final_message(provider)
    finally:
        await provider.close()
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"a": 1}


def test_anthropic_history_with_empty_arguments_is_replayed_as_empty_object():
    provider = AnthropicProvider(api_key="k", model="m", native_vision=True)
    logger = _RecordingLogger()
    provider._logger = logger
    history = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {"name": "list_agents", "arguments": ""},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "content": "ok"},
    ]
    _, converted = provider._convert_messages(history)
    assert converted[1]["content"][0]["input"] == {}
    # 空串 = 无参数，不是损坏，不应产生修复告警。
    assert logger.warnings == []


def test_anthropic_history_with_broken_arguments_is_repaired_and_reported():
    provider = AnthropicProvider(api_key="k", model="m", native_vision=True)
    logger = _RecordingLogger()
    provider._logger = logger
    _, converted = provider._convert_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "toolu_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": '},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "toolu_1", "content": "ok"},
        ]
    )
    assert converted[0]["content"][0]["input"] == {}
    assert len(logger.warnings) == 1
    assert "raw_arguments" in logger.warnings[0][1]


def test_anthropic_history_with_non_object_arguments_is_repaired():
    provider = AnthropicProvider(api_key="k", model="m", native_vision=True)
    _, converted = provider._convert_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "toolu_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "[1, 2]"},
                    }
                ],
            }
        ]
    )
    assert converted[0]["content"][0]["input"] == {}


@pytest.mark.asyncio
async def test_anthropic_chat_maps_null_tool_input_to_empty_object():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "f", "input": None}
                ],
                "stop_reason": "tool_use",
            },
        )

    provider = AnthropicProvider(api_key="k", model="m")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://example.com"
    )
    try:
        message = await provider.chat([{"role": "user", "content": "hi"}])
    finally:
        await provider.close()
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {}


# ── OpenAI / DeepSeek：同一根因的出口加固 ────────────────────────


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
@pytest.mark.asyncio
async def test_openai_compatible_stream_tool_call_without_arguments_gets_empty_object(provider_cls):
    body = (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {"name": "list_agents", "arguments": ""},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        + "\n"
        "data: [DONE]\n"
    )
    provider = _provider_with_sse(provider_cls, body)
    try:
        message = await _final_message(provider)
    finally:
        await provider.close()
    assert message["tool_calls"][0]["function"]["arguments"] == "{}"


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
def test_payload_normalizes_blank_history_arguments_without_mutating_history(provider_cls):
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "list_agents", "arguments": ""},
    }
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [tool_call]},
        {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
    ]
    provider = provider_cls(api_key="k", model="m")
    if provider_cls is OpenAIProvider:
        payload = provider._build_payload(history, None, stream=False)
        sent = payload["messages"][1]["tool_calls"]
    else:
        sent = provider._serialize_messages(history)[1]["tool_calls"]
    assert sent[0]["function"]["arguments"] == "{}"
    # 出口修复不得改写调用方持有的历史对象。
    assert history[1]["tool_calls"][0]["function"]["arguments"] == ""


@pytest.mark.parametrize("provider_cls", [OpenAIProvider, DeepSeekOfficalProvider])
def test_payload_keeps_valid_history_arguments_untouched(provider_cls):
    raw = '{"path": "a.txt"}'
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "read_file", "arguments": raw},
    }
    history = [{"role": "assistant", "content": None, "tool_calls": [tool_call]}]
    provider = provider_cls(api_key="k", model="m")
    if provider_cls is OpenAIProvider:
        sent = provider._build_payload(history, None, stream=False)["messages"][0]["tool_calls"]
    else:
        sent = provider._serialize_messages(history)[0]["tool_calls"]
    assert sent[0]["function"]["arguments"] == raw


# ── 共享 helper 的直接契约 ───────────────────────────────────────


def test_tool_arguments_object_distinguishes_missing_from_broken():
    assert tool_arguments_object("") == {}
    assert tool_arguments_object("   ") == {}
    assert tool_arguments_object(None) == {}
    assert tool_arguments_object('{"a": 1}') == {"a": 1}

    repaired: list[tuple[str, str]] = []
    assert tool_arguments_object("{", on_invalid=lambda raw, why: repaired.append((raw, why))) == {}
    assert len(repaired) == 1
    assert repaired[0][0] == "{"

    missing: list[tuple[str, str]] = []
    assert tool_arguments_object("", on_invalid=lambda raw, why: missing.append((raw, why))) == {}
    assert missing == []


def test_normalized_tool_calls_returns_same_list_when_nothing_to_repair():
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "f", "arguments": "{}"},
    }
    calls = [tool_call]
    assert normalized_tool_calls(calls) is calls
    assert tool_arguments_text("") == "{}"
    assert tool_arguments_text(" {} ") == " {} "
