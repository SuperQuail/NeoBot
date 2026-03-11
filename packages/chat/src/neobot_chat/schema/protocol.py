from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from neobot_chat.schema.types import ChatChunk, State, ToolDefinition, ToolGuardContext

StatePreprocessor = Callable[[State], State]
ToolGuard = Callable[[str, dict, ToolGuardContext], bool | Awaitable[bool]]


class Runnable(Protocol):
    async def invoke(self, state: State) -> State: ...


class StreamableRunnable(Runnable, Protocol):
    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]: ...


class ChatService(StreamableRunnable, Protocol):
    async def close(self) -> None: ...


class AgentLike(ChatService, Protocol):
    description: str
    tool_definitions: list[ToolDefinition]


class ToolExecutor(Protocol):
    def definitions(self) -> list[ToolDefinition]: ...

    async def execute(self, name: str, args: dict) -> str: ...

    async def close(self) -> None: ...
