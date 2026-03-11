from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from neobot_chat.providers.base import BaseHTTPProvider
from neobot_chat.schema.types import ChatChunk, Message, ToolCall, ToolDefinition


class DeepSeekOfficalProvider(BaseHTTPProvider):
    """DeepSeek 官方 Chat Completions API"""

    SUPPORTED_MODELS = {"deepseek-chat", "deepseek-reasoner"}

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout: float = 120.0,
    ):
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported DeepSeek official model: {model}. "
                f"Expected one of: {', '.join(sorted(self.SUPPORTED_MODELS))}"
            )
        super().__init__(api_key, base_url, timeout)
        self.model = model

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def _is_reasoner(self) -> bool:
        return self.model == "deepseek-reasoner"

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
            if self._is_reasoner and reasoning_content:
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
        raise RuntimeError(f"DeepSeek API error {response.status_code}: {body}")

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

        payload["thinking"] = {"type": "enabled" if self._is_reasoner else "disabled"}
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
