from __future__ import annotations

import json
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from neobot_chat.providers.base import BaseHTTPProvider
from neobot_chat.schema.exceptions import ProviderError
from neobot_chat.schema.types import ChatChunk, Message, ToolCall, ToolDefinition


class DeepSeekOfficalProvider(BaseHTTPProvider):
    """DeepSeek 官方 Chat Completions API"""

    _THINKING_MODE_KEY = "__deepseek_thinking_mode__"
    _REASONING_EFFORT_KEY = "__deepseek_reasoning_effort__"
    _THINKING_PROBABILITY_KEY = "__deepseek_random_thinking_probability__"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout: float = 120.0,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        super().__init__(api_key, base_url, timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.extra_body = extra_body or {}

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def _is_reasoner(self) -> bool:
        return self.model == "deepseek-reasoner"

    @staticmethod
    def _detect_thinking_format() -> str:
        """自动检测思考模式参数格式。

        根据当前 Provider 类型返回对应的参数格式：
        - DeepSeek / OpenAI 兼容 API → ``"openai"``
        - Anthropic API → ``"anthropic"``

        默认为 ``"openai"`` 格式，子类可重写以适配不同 API。
        """
        return "openai"

    def _resolve_extra_body(self) -> tuple[dict[str, Any], str, str | None, float]:
        extra_body = dict(self.extra_body)

        thinking_mode = self._normalize_thinking_mode(
            extra_body.pop(
                self._THINKING_MODE_KEY,
                extra_body.pop(
                    "deepseek_thinking_mode",
                    True if self._is_reasoner else False,
                ),
            )
        )

        reasoning_effort_raw = extra_body.pop(
            self._REASONING_EFFORT_KEY,
            extra_body.pop("deepseek_reasoning_effort", extra_body.pop("reasoning_effort", None)),
        )
        reasoning_effort = (
            str(reasoning_effort_raw).strip().casefold()
            if reasoning_effort_raw is not None
            else None
        )
        reasoning_effort = self._normalize_reasoning_effort(reasoning_effort)

        probability_raw = extra_body.pop(
            self._THINKING_PROBABILITY_KEY,
            extra_body.pop("deepseek_random_thinking_probability", 0.6),
        )
        try:
            thinking_probability = float(probability_raw)
        except (TypeError, ValueError):
            thinking_probability = 0.6
        thinking_probability = max(0.0, min(1.0, thinking_probability))

        extra_body.pop("thinking", None)
        return extra_body, thinking_mode, reasoning_effort, thinking_probability

    def _build_thinking_payload(self) -> tuple[dict[str, str], str | None, dict[str, Any]]:
        extra_body, thinking_mode, reasoning_effort, thinking_probability = (
            self._resolve_extra_body()
        )

        enabled = thinking_mode == "true"
        if thinking_mode == "random":
            enabled = random.random() < thinking_probability

        thinking_payload = {"type": "enabled" if enabled else "disabled"}
        effective_reasoning_effort = reasoning_effort if enabled else None
        return thinking_payload, effective_reasoning_effort, extra_body

    @staticmethod
    def _normalize_thinking_mode(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        normalized = str(value).strip().casefold()
        if normalized in {"true", "1", "yes", "on", "enabled", "enable"}:
            return "true"
        if normalized == "random":
            return "random"
        return "false"

    @staticmethod
    def _normalize_reasoning_effort(value: str | None) -> str | None:
        """标准化思考强度值，兼容 low/medium→high, xhigh→max 映射。"""
        if value is None:
            return None
        if value in {"low", "medium"}:
            return "high"
        if value == "xhigh":
            return "max"
        if value in {"high", "max"}:
            return value
        return None

    @staticmethod
    def _build_tool_call(
        *, tool_id: object, tool_name: object, arguments: object
    ) -> ToolCall | None:
        if not isinstance(tool_id, str) or not isinstance(tool_name, str):
            return None

        if isinstance(arguments, str):
            parsed_arguments = arguments
        else:
            parsed_arguments = json.dumps(arguments if arguments is not None else {})

        tool_call: ToolCall = {
            "id": tool_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": parsed_arguments,
            },
        }
        return tool_call

    @staticmethod
    def _get_reasoning_content(message: Message) -> str | None:
        extensions = message.get("extensions")
        if not isinstance(extensions, dict):
            return None
        deepseek = extensions.get("deepseek")
        if not isinstance(deepseek, dict):
            return None
        reasoning_content = deepseek.get("reasoning_content")
        return (
            reasoning_content
            if isinstance(reasoning_content, str) and reasoning_content
            else None
        )

    @staticmethod
    def _set_reasoning_content(message: Message, reasoning_content: str) -> None:
        extensions = message.get("extensions")
        if not isinstance(extensions, dict):
            extensions = {}
            message["extensions"] = extensions
        deepseek = extensions.get("deepseek")
        if not isinstance(deepseek, dict):
            deepseek = {}
            extensions["deepseek"] = deepseek
        deepseek["reasoning_content"] = reasoning_content

    def _serialize_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            payload: dict[str, Any] = {"role": message["role"]}

            if "content" in message:
                payload["content"] = message.get("content")
            if "tool_call_id" in message:
                payload["tool_call_id"] = message["tool_call_id"]
            if "tool_calls" in message:
                payload["tool_calls"] = message["tool_calls"]

            reasoning_content = self._get_reasoning_content(message)
            if reasoning_content:
                payload["reasoning_content"] = reasoning_content

            serialized.append(payload)

        return serialized

    async def _raise_for_status_with_body(self, response: httpx.Response) -> None:
        if not response.is_error:
            return
        try:
            body = response.text
        except Exception:
            try:
                body = (await response.aread()).decode("utf-8", errors="replace")
            except Exception:
                body = "<unable to read response body>"
        raise ProviderError(f"DeepSeek API error {response.status_code}: {body}")

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._serialize_messages(messages),
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        thinking_payload, reasoning_effort, extra_body = self._build_thinking_payload()
        payload["thinking"] = thinking_payload

        if reasoning_effort is not None:
            fmt = self._detect_thinking_format()
            if fmt == "anthropic":
                payload["output_config"] = {"effort": reasoning_effort}
            else:
                payload["reasoning_effort"] = reasoning_effort
        self._apply_payload_options(
            payload,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            extra_body=extra_body,
        )
        return payload

    def _parse_message(self, raw_message: dict[str, Any]) -> Message:
        content = raw_message.get("content")
        reasoning_content = raw_message.get("reasoning_content")
        result: Message = {
            "role": "assistant",
            "content": content,
        }
        if isinstance(reasoning_content, str) and reasoning_content:
            self._set_reasoning_content(result, reasoning_content)

        tool_calls: list[ToolCall] = []
        for tc in raw_message.get("tool_calls", []):
            function = tc.get("function", {})
            tool_call = self._build_tool_call(
                tool_id=tc.get("id"),
                tool_name=function.get("name"),
                arguments=function.get("arguments"),
            )
            if tool_call is not None:
                tool_calls.append(tool_call)

        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> Message:
        resp = await self.client.post(
            "/chat/completions",
            json=self._build_payload(messages, tools, stream=False),
        )
        await self._raise_for_status_with_body(resp)
        data = resp.json()
        return self._parse_message(data["choices"][0]["message"])

    async def stream(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[ChatChunk]:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_map: dict[int, ToolCall] = {}

        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=self._build_payload(messages, tools, stream=True),
        ) as resp:
            await self._raise_for_status_with_body(resp)
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                data = json.loads(data_str)
                choices = data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                reasoning_content = delta.get("reasoning_content")
                if isinstance(reasoning_content, str) and reasoning_content:
                    reasoning_parts.append(reasoning_content)
                    yield ChatChunk(reasoning_delta=reasoning_content)

                content = delta.get("content")
                if isinstance(content, str) and content:
                    content_parts.append(content)
                    yield ChatChunk(delta=content)

                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index")
                    if not isinstance(idx, int):
                        continue
                    if idx not in tool_calls_map:
                        tool_call = self._build_tool_call(
                            tool_id=tc_delta.get("id", ""),
                            tool_name="",
                            arguments="",
                        )
                        if tool_call is None:
                            continue
                        tool_calls_map[idx] = tool_call
                    entry = tool_calls_map[idx]
                    fn = tc_delta.get("function", {})
                    name = fn.get("name")
                    if isinstance(name, str) and name:
                        entry["function"]["name"] += name
                    arguments = fn.get("arguments")
                    if isinstance(arguments, str) and arguments:
                        entry["function"]["arguments"] += arguments

        message: Message = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
        }
        if reasoning_parts:
            self._set_reasoning_content(message, "".join(reasoning_parts))
        if tool_calls_map:
            message["tool_calls"] = [tool_calls_map[i] for i in sorted(tool_calls_map)]
        yield ChatChunk(message=message)


DeepSeekOfficialProvider = DeepSeekOfficalProvider
