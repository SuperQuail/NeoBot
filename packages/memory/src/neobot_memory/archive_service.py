"""Archive memory service."""

from __future__ import annotations

from typing import Optional

from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


class ArchiveMemoryService:
    """Service for archive memory CRUD and query operations."""

    def __init__(self, uow_factory: UnitOfWorkFactory, logger: Logger) -> None:
        self._uow_factory = uow_factory
        self._logger = logger

    async def get(self, table_name: str, key: str) -> Optional[ArchiveMemory]:
        async with self._uow_factory() as uow:
            item = await uow.archive.get(table_name, key)
        self._logger.debug("存档记忆已获取", table_name=table_name, key=key, found=item is not None)
        return item

    async def exists(self, table_name: str, key: str) -> bool:
        async with self._uow_factory() as uow:
            exists = await uow.archive.exists(table_name, key)
        self._logger.debug("存档记忆存在检查", table_name=table_name, key=key, exists=exists)
        return exists

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
        async with self._uow_factory() as uow:
            items = await uow.archive.list(
                table_name,
                tags=tags,
                key_query=key_query,
                value_query=value_query,
                limit=limit,
                offset=offset,
            )
        self._logger.debug(
            "存档记忆列表已获取",
            table_name=table_name,
            count=len(items),
            limit=limit,
            offset=offset,
        )
        return items

    async def set(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        async with self._uow_factory() as uow:
            item = await uow.archive.set(table_name, key, value, tags)
            await uow.commit()
        self._logger.debug(
            "存档记忆已保存",
            table_name=table_name,
            key=key,
            version=item.version,
        )
        return item

    async def delete(self, table_name: str, key: str) -> bool:
        async with self._uow_factory() as uow:
            deleted = await uow.archive.delete(table_name, key)
            if deleted:
                await uow.commit()
        self._logger.debug("存档记忆已删除", table_name=table_name, key=key, deleted=deleted)
        return deleted
