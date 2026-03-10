from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from neobot_chat.providers.base import BaseHTTPProvider
from neobot_chat.types import ChatChunk


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

    async def chat(
            self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
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
        result: dict[str, Any] = {
            "role": "assistant",
            "content": choice.get("content"),
        }

        if choice.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in choice["tool_calls"]
            ]

        return result

    # ── 流式 API ──

    async def stream(
            self, messages: list[dict], tools: list[dict] | None = None
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
        tool_calls_map: dict[int, dict] = {}

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

                if delta.get("content"):
                    content_parts.append(delta["content"])
                    yield ChatChunk(delta=delta["content"])

                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta["index"]
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    entry = tool_calls_map[idx]
                    fn = tc_delta.get("function", {})
                    if fn.get("name"):
                        entry["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        entry["function"]["arguments"] += fn["arguments"]

        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
        }
        if tool_calls_map:
            message["tool_calls"] = [
                tool_calls_map[i] for i in sorted(tool_calls_map)
            ]
        yield ChatChunk(message=message)
