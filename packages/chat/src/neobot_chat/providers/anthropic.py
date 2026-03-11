from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from neobot_chat.providers.base import BaseHTTPProvider
from neobot_chat.schema.types import ChatChunk, Message, ToolCall, ToolDefinition
from neobot_chat.utils import parse_tool_args


class AnthropicProvider(BaseHTTPProvider):
    """Anthropic Messages API"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        super().__init__(api_key, base_url, timeout)
        self.model = model
        self.max_tokens = max_tokens

    def _build_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    # ── 格式转换：OpenAI → Anthropic ──

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict]]:
        system_parts: list[str] = []
        converted: list[dict] = []
        for msg in messages:
            match msg["role"]:
                case "system":
                    content = msg.get("content")
                    if isinstance(content, str) and content:
                        system_parts.append(content)
                case "assistant":
                    converted.append(self._convert_assistant_msg(msg))
                case "tool":
                    converted.append(self._convert_tool_msg(msg))
                case _:
                    converted.append({"role": "user", "content": msg.get("content")})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, converted

    @staticmethod
    def _convert_assistant_msg(msg: Message) -> dict:
        blocks: list[dict] = []
        content = msg.get("content")
        if isinstance(content, str) and content:
            blocks.append({"type": "text", "text": content})
        elif isinstance(content, list):
            blocks.extend(block for block in content if isinstance(block, dict))
        for tc in msg.get("tool_calls", []):
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": parse_tool_args(tc["function"]["arguments"]),
                }
            )
        return {"role": "assistant", "content": blocks}

    @staticmethod
    def _convert_tool_msg(msg: Message) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
            ],
        }

    @staticmethod
    def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object"}),
            }
            for t in tools
        ]

    # ── API 调用 ──

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> Message:
        system, converted_messages = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted_messages,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._convert_tools(tools)

        resp = await self.client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        return self._parse_response(resp.json())

    @staticmethod
    def _parse_response(data: dict) -> Message:
        result: Message = {"role": "assistant", "content": None}
        tool_calls: list[ToolCall] = []

        for block in data.get("content", []):
            block_type = block.get("type")
            match block_type:
                case "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        result["content"] = text
                case "tool_use":
                    tool_call = AnthropicProvider._build_tool_call(
                        tool_id=block.get("id"),
                        tool_name=block.get("name"),
                        arguments=json.dumps(block.get("input", {})),
                    )
                    if tool_call is not None:
                        tool_calls.append(tool_call)

        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    @staticmethod
    def _build_tool_call(
        *, tool_id: object, tool_name: object, arguments: str
    ) -> ToolCall | None:
        if not isinstance(tool_id, str) or not isinstance(tool_name, str):
            return None
        tool_call: ToolCall = {
            "id": tool_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        return tool_call

    # ── 流式 API ──

    async def stream(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[ChatChunk]:
        system, converted_messages = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted_messages,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._convert_tools(tools)

        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        current_tool: ToolCall | None = None

        async with self.client.stream("POST", "/v1/messages", json=payload) as resp:
            resp.raise_for_status()
            event_type = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                    continue
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])

                match event_type:
                    case "content_block_start":
                        block = data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool = self._build_tool_call(
                                tool_id=block.get("id"),
                                tool_name=block.get("name"),
                                arguments="",
                            )

                    case "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                content_parts.append(text)
                                yield ChatChunk(delta=text)
                        elif delta.get("type") == "input_json_delta" and current_tool:
                            partial_json = delta.get("partial_json")
                            if isinstance(partial_json, str):
                                current_tool["function"]["arguments"] += partial_json

                    case "content_block_stop":
                        if current_tool:
                            tool_calls.append(current_tool)
                            current_tool = None

                    case "message_stop":
                        break

        message: Message = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls
        yield ChatChunk(message=message)
