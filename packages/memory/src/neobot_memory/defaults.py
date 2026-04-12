"""Defaults — 开箱即用的默认实现"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from neobot_contracts.models import ConversationRef, MemoryRecord
from neobot_contracts.models.memory import ArchiveMemory, ImageAnalysis
from neobot_contracts.ports.archive_memory_access import ArchiveMemoryAccess
from neobot_contracts.ports.image_analysis_access import ImageAnalysisAccess
from neobot_contracts.ports.clock import SystemClock as SystemClock  # re-export
from neobot_contracts.ports.logging import NullLogger as NullLogger  # re-export


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


class InMemoryArchiveMemoryAccess:
    """内存档案式记忆存储，用于测试或独立运行"""

    def __init__(self) -> None:
        self._storage: dict[tuple[str, str], ArchiveMemory] = {}
        self._id_counter = 0

    async def get(self, table_name: str, key: str) -> Optional[ArchiveMemory]:
        """根据表名和键名获取档案式记忆条目"""
        entry = self._storage.get((table_name, key))
        if entry is None:
            return None
        return self._clone(entry)

    async def set(
        self,
        table_name: str,
        key: str,
        value: str,
        tags: list[str],
    ) -> ArchiveMemory:
        """创建或更新档案式记忆条目"""
        entry_key = (table_name, key)

        if entry_key in self._storage:
            # 更新现有条目
            existing = self._storage[entry_key]
            updated = ArchiveMemory(
                id=existing.id,
                table_name=table_name,
                key=key,
                value=value,
                tags=tags.copy(),  # 创建副本避免外部修改
                created_at=existing.created_at,  # 保留原始创建时间
                updated_at=datetime.now(timezone.utc),
                version=existing.version + 1,
            )
        else:
            # 创建新条目
            self._id_counter += 1
            now = datetime.now(timezone.utc)
            updated = ArchiveMemory(
                id=self._id_counter,
                table_name=table_name,
                key=key,
                value=value,
                tags=tags.copy(),
                created_at=now,
                updated_at=now,
                version=1,
            )

        self._storage[entry_key] = self._clone(updated)
        return self._clone(updated)

    async def delete(self, table_name: str, key: str) -> bool:
        """删除档案式记忆条目"""
        entry_key = (table_name, key)
        if entry_key in self._storage:
            del self._storage[entry_key]
            return True
        return False

    async def exists(self, table_name: str, key: str) -> bool:
        """检查档案式记忆条目是否存在"""
        return (table_name, key) in self._storage

    async def list(
        self,
        table_name: str,
        *,
        tags: Optional[list[str]] = None,
        key_query: Optional[str] = None,
        value_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]:
        """列出符合条件的档案式记忆条目"""
        rows = [
            self._clone(entry)
            for (stored_table_name, _), entry in self._storage.items()
            if stored_table_name == table_name
        ]

        if tags:
            rows = [row for row in rows if all(tag in row.tags for tag in tags)]
        if key_query:
            lowered_key_query = key_query.lower()
            rows = [row for row in rows if lowered_key_query in row.key.lower()]
        if value_query:
            lowered_value_query = value_query.lower()
            rows = [row for row in rows if lowered_value_query in row.value.lower()]

        rows.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
        return rows[offset : offset + limit]

    # Type check: ensure class implements the protocol
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        # Verify that this class implements the ArchiveMemoryAccess protocol
        if not issubclass(cls, ArchiveMemoryAccess):  # type: ignore
            raise TypeError(f"{cls.__name__} does not implement ArchiveMemoryAccess protocol")

    @staticmethod
    def _clone(entry: ArchiveMemory) -> ArchiveMemory:
        return ArchiveMemory(
            id=entry.id,
            table_name=entry.table_name,
            key=entry.key,
            value=entry.value,
            tags=entry.tags.copy(),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            version=entry.version,
        )


class InMemoryImageAnalysisAccess:
    """In-memory image analysis cache for tests and standalone runs."""

    def __init__(self) -> None:
        self._storage: dict[str, ImageAnalysis] = {}
        self._id_counter = 0

    async def get(self, file_hash: str) -> Optional[ImageAnalysis]:
        entry = self._storage.get(file_hash)
        if entry is None:
            return None
        return self._clone(entry)

    async def set(
        self,
        file_hash: str,
        *,
        source: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        processed_width: Optional[int] = None,
        processed_height: Optional[int] = None,
        analysis_text: Optional[str] = None,
    ) -> ImageAnalysis:
        if file_hash in self._storage:
            existing = self._storage[file_hash]
            updated = ImageAnalysis(
                id=existing.id,
                file_hash=file_hash,
                source=source if source is not None else existing.source,
                mime_type=mime_type if mime_type is not None else existing.mime_type,
                original_width=original_width if original_width is not None else existing.original_width,
                original_height=original_height if original_height is not None else existing.original_height,
                processed_width=processed_width if processed_width is not None else existing.processed_width,
                processed_height=processed_height if processed_height is not None else existing.processed_height,
                analysis_text=analysis_text if analysis_text is not None else existing.analysis_text,
                created_at=existing.created_at,
                updated_at=datetime.now(timezone.utc),
                version=existing.version + 1,
            )
        else:
            self._id_counter += 1
            now = datetime.now(timezone.utc)
            updated = ImageAnalysis(
                id=self._id_counter,
                file_hash=file_hash,
                source=source,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                processed_width=processed_width,
                processed_height=processed_height,
                analysis_text=analysis_text,
                created_at=now,
                updated_at=now,
                version=1,
            )

        self._storage[file_hash] = self._clone(updated)
        return self._clone(updated)

    async def delete(self, file_hash: str) -> bool:
        if file_hash in self._storage:
            del self._storage[file_hash]
            return True
        return False

    async def exists(self, file_hash: str) -> bool:
        return file_hash in self._storage

    async def list(
        self,
        *,
        source_query: Optional[str] = None,
        has_analysis_text: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageAnalysis]:
        rows = [self._clone(entry) for entry in self._storage.values()]

        if source_query:
            lowered = source_query.lower()
            rows = [row for row in rows if row.source and lowered in row.source.lower()]
        if has_analysis_text is True:
            rows = [row for row in rows if row.analysis_text]
        elif has_analysis_text is False:
            rows = [row for row in rows if not row.analysis_text]

        rows.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
        return rows[offset : offset + limit]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if not issubclass(cls, ImageAnalysisAccess):  # type: ignore[arg-type]
            raise TypeError(f"{cls.__name__} does not implement ImageAnalysisAccess protocol")

    @staticmethod
    def _clone(entry: ImageAnalysis) -> ImageAnalysis:
        return ImageAnalysis(
            id=entry.id,
            file_hash=entry.file_hash,
            source=entry.source,
            mime_type=entry.mime_type,
            original_width=entry.original_width,
            original_height=entry.original_height,
            processed_width=entry.processed_width,
            processed_height=entry.processed_height,
            analysis_text=entry.analysis_text,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            version=entry.version,
        )
