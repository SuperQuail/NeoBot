"""Memory Ports — 记忆系统抽象"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from neobot_contracts.models.memory import ArchiveMemory, TopicNode


@runtime_checkable
class ArchiveStorage(Protocol):
    """档案式记忆存储接口"""

    async def set(
        self,
        table_name: str,
        key: str,
        value: str,
        tags: list[str],
    ) -> ArchiveMemory: ...

    async def delete(self, table_name: str, key: str) -> bool: ...


@runtime_checkable
class ArchiveQuery(Protocol):
    """档案式记忆查询接口"""

    async def get(
        self,
        table_name: str,
        key: str,
    ) -> Optional[ArchiveMemory]: ...

    async def exists(self, table_name: str, key: str) -> bool: ...

    async def list(
        self,
        table_name: str,
        tags: Optional[list[str]] = None,
        key_query: Optional[str] = None,
        value_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]: ...


@runtime_checkable
class TopicStorage(Protocol):
    """话题树存储"""

    async def create_node(
        self,
        title: str,
        content: str,
        embedding: list[float],
        node_type: str,
        tags: list[str],
        parent_id: Optional[int] = None,
    ) -> int: ...

    async def update_node(
        self, node_id: int, content: str, embedding: list[float], tags: list[str]
    ) -> None: ...

    async def delete_node(self, node_id: int) -> None: ...


@runtime_checkable
class TopicQuery(Protocol):
    """话题树查询"""

    async def get_node(self, node_id: int) -> Optional[TopicNode]: ...

    async def get_children(self, node_id: int) -> list[TopicNode]: ...

    async def get_context(self, node_id: int) -> list[TopicNode]: ...

    async def search_by_tags(self, tags: list[str], limit: int = 10) -> list[TopicNode]: ...

    async def search_by_content(self, query: str, limit: int = 10) -> list[TopicNode]: ...

    async def search_by_vector(
        self, query: str, limit: int = 10
    ) -> list[TopicNode]: ...

    async def search_by_embedding(
        self, embedding: list[float], limit: int = 10
    ) -> list[TopicNode]: ...
