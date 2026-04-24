"""Inbound pipeline for normalized incoming messages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_adapter.mapping import map_to_incoming_message
from neobot_contracts.models import IncomingMessage
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import MemoryService

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


class InboundPipeline:
    """Normalize inbound messages and persist short-term memory."""

    def __init__(
        self,
        adapter: OneBotAdapter,
        memory: MemoryService | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._memory = memory
        self._logger = logger or NullLogger()

    async def handle(self, message: IncomingMessage) -> None:
        self._logger.info(
            "收到入站消息",
            conversation_kind=message.conversation.kind,
            conversation_id=message.conversation.id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            preview=message.text[:80],
        )

        if self._memory is None:
            return

        try:
            await self._memory.remember(
                conversation_id=f"{message.conversation.kind}:{message.conversation.id}",
                speaker_id=message.sender_id,
                content=message.text,
            )
        except Exception as exc:
            self._logger.error("记忆存储失败", error=str(exc))

    async def handle_raw_event(self, raw_event: dict[str, Any]) -> None:
        await self.handle(map_to_incoming_message(raw_event))
