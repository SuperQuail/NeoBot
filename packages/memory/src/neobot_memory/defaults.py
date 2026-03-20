"""Defaults — 开箱即用的默认实现"""

from __future__ import annotations

from neobot_contracts.models import ConversationRef, MemoryRecord
from neobot_contracts.ports.clock import SystemClock as SystemClock  # re-export
from neobot_contracts.ports.logging import NullLogger as NullLogger  # re-export
from neobot_contracts.ports.repository import MemoryRepository


class InMemoryMemoryRepository:
    """纯内存记忆存储，用于测试或独立运行"""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    async def save(self, record: MemoryRecord) -> None:
        self._records.append(record)

    async def search(
        self, conversation: ConversationRef, query: str, limit: int = 5
    ) -> list[MemoryRecord]:
        matches = [
            r for r in self._records
            if r.conversation == conversation and query.lower() in r.content.lower()
        ]
        return matches[-limit:]
