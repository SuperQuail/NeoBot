"""MemoryReader Protocol — 记忆读取抽象"""

from __future__ import annotations

from typing import Protocol


class MemoryReader(Protocol):
    """记忆读取协议，MemoryService 结构性满足此协议"""

    async def recall(
        self, conversation_id: str, query: str, limit: int = 5
    ) -> list[str]: ...
