"""MemoryService — 记忆读写服务"""

from __future__ import annotations

from neobot_contracts.models import ConversationRef, MemoryRecord
from neobot_contracts.ports.clock import Clock
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.repository import MemoryRepository


class MemoryService:
    """记忆服务，负责存储和检索记忆条目"""

    def __init__(
        self,
        repository: MemoryRepository,
        logger: Logger,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._clock = clock

    async def remember(
        self, conversation_id: str, speaker_id: str, content: str
    ) -> None:
        record = MemoryRecord(
            conversation=ConversationRef(kind="private", id=conversation_id),
            speaker_id=speaker_id,
            content=content,
            created_at=self._clock.now(),
        )
        await self._repository.save(record)
        self._logger.debug("memory saved", conversation_id=conversation_id, speaker_id=speaker_id)

    async def recall(
        self, conversation_id: str, query: str, limit: int = 5
    ) -> list[str]:
        ref = ConversationRef(kind="private", id=conversation_id)
        records = await self._repository.search(ref, query, limit)
        self._logger.debug(
            "memory recalled",
            conversation_id=conversation_id,
            count=len(records),
        )
        return [r.content for r in records]
