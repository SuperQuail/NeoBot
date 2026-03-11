from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from neobot_chat.providers.base import BaseHTTPProvider
from neobot_chat.schema.types import ChatChunk, Message, ToolCall, ToolDefinition


class OpenAIProvider(BaseHTTPProvider):
    """OpenAI Chat Completions API"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ):
        super().__init__(api_key, base_url, timeout)
        self.model = model

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> Message:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = await self.client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]["message"]
        content = choice.get("content")
        result: Message = {
            "role": "assistant",
            "content": content if isinstance(content, str) else None,
        }

        tool_calls: list[ToolCall] = []
        for tc in choice.get("tool_calls", []):
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

    # ── 流式 API ──

    async def stream(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[ChatChunk]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        content_parts: list[str] = []
        tool_calls_map: dict[int, ToolCall] = {}

        async with self.client.stream(
            "POST", "/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
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
        if tool_calls_map:
            message["tool_calls"] = [tool_calls_map[i] for i in sorted(tool_calls_map)]
        yield ChatChunk(message=message)
