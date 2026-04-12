"""Archive Memory Access Port — 档案式记忆读写接口

提供通过表名和键名获取和更新档案式记忆条目的函数接口。
如果输入的表名或键名是 int、float、bool 等类型，会自动转换成 str。

示例：
    ```python
    from neobot_contracts.ports import ArchiveMemoryAccess

    class MyArchiveMemoryAccess(ArchiveMemoryAccess):
        async def get(self, table_name: str, key: str):
            # 实现获取逻辑
            ...
        # 其他方法...

    # 使用包装器自动类型转换
    from neobot_contracts.ports import ArchiveMemoryAccessWrapper, ensure_str

    access = MyArchiveMemoryAccess()
    wrapper = ArchiveMemoryAccessWrapper(access)

    # 自动将整数键转换为字符串
    memory = await wrapper.get("users", 123)
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable, Union

if TYPE_CHECKING:
    from neobot_contracts.models.memory import ArchiveMemory


@runtime_checkable
class ArchiveMemoryAccess(Protocol):
    """档案式记忆读写接口
    
    提供通过表名和键名获取和更新档案式记忆条目的功能。
    如果输入的表名或键名是 int 等类型，会自动转换成 str。
    """

    async def get(
        self, 
        table_name: str, 
        key: str
    ) -> Optional[ArchiveMemory]:
        """根据表名和键名获取档案式记忆条目
        
        Args:
            table_name: 表名，用于区分不同类别的记忆
            key: 键名，在表内唯一标识一个条目
            
        Returns:
            如果找到则返回 ArchiveMemory 对象，否则返回 None
        """
        ...

    async def set(
        self,
        table_name: str,
        key: str,
        value: str,
        tags: list[str],
    ) -> ArchiveMemory:
        """创建或更新档案式记忆条目
        
        如果指定的表名和键名已存在，则更新该条目；
        如果不存在，则创建新条目。
        
        Args:
            table_name: 表名
            key: 键名
            value: 值
            tags: 标签列表
            
        Returns:
            创建或更新后的 ArchiveMemory 对象
        """
        ...

    async def delete(
        self,
        table_name: str,
        key: str,
    ) -> bool:
        """删除档案式记忆条目
        
        Args:
            table_name: 表名
            key: 键名
            
        Returns:
            如果成功删除返回 True，如果条目不存在返回 False
        """
        ...

    async def exists(
        self,
        table_name: str,
        key: str,
    ) -> bool:
        """检查档案式记忆条目是否存在
        
        Args:
            table_name: 表名
            key: 键名
            
        Returns:
            如果条目存在返回 True，否则返回 False
        """
        ...

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
        """按条件列出给定表的档案式记忆条目"""
        ...


def ensure_str(value: Union[str, int, float, bool, None]) -> str:
    """确保输入值为字符串类型
    
    如果输入值是 int、float、bool 等类型，会自动转换为 str。
    如果输入值是 None，会抛出 ValueError。
    
    Args:
        value: 输入值
        
    Returns:
        字符串表示
    """
    if value is None:
        raise ValueError("table_name and key cannot be None")
    return str(value)


def ensure_optional_str(value: Union[str, int, float, bool, None]) -> Optional[str]:
    """确保输入值为可选字符串类型"""
    if value is None:
        return None
    return str(value)


class ArchiveMemoryAccessWrapper:
    """ArchiveMemoryAccess 包装器，自动处理类型转换"""
    
    def __init__(self, access: ArchiveMemoryAccess):
        self._access = access
    
    async def get(
        self,
        table_name: Union[str, int, float, bool, None],
        key: Union[str, int, float, bool, None],
    ) -> Optional[ArchiveMemory]:
        """根据表名和键名获取档案式记忆条目（自动类型转换）"""
        table_name_str = ensure_str(table_name)
        key_str = ensure_str(key)
        return await self._access.get(table_name_str, key_str)
    
    async def set(
        self,
        table_name: Union[str, int, float, bool, None],
        key: Union[str, int, float, bool, None],
        value: str,
        tags: list[str],
    ) -> ArchiveMemory:
        """创建或更新档案式记忆条目（自动类型转换）"""
        table_name_str = ensure_str(table_name)
        key_str = ensure_str(key)
        return await self._access.set(table_name_str, key_str, value, tags)
    
    async def delete(
        self,
        table_name: Union[str, int, float, bool, None],
        key: Union[str, int, float, bool, None],
    ) -> bool:
        """删除档案式记忆条目（自动类型转换）"""
        table_name_str = ensure_str(table_name)
        key_str = ensure_str(key)
        return await self._access.delete(table_name_str, key_str)
    
    async def exists(
        self,
        table_name: Union[str, int, float, bool, None],
        key: Union[str, int, float, bool, None],
    ) -> bool:
        """检查档案式记忆条目是否存在（自动类型转换）"""
        table_name_str = ensure_str(table_name)
        key_str = ensure_str(key)
        return await self._access.exists(table_name_str, key_str)

    async def list(
        self,
        table_name: Union[str, int, float, bool, None],
        *,
        tags: Optional[list[Union[str, int, float, bool, None]]] = None,
        key_query: Union[str, int, float, bool, None] = None,
        value_query: Union[str, int, float, bool, None] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]:
        """列出档案式记忆条目（自动类型转换）"""
        table_name_str = ensure_str(table_name)
        normalized_tags = [ensure_str(tag) for tag in tags] if tags is not None else None
        return await self._access.list(
            table_name_str,
            tags=normalized_tags,
            key_query=ensure_optional_str(key_query),
            value_query=ensure_optional_str(value_query),
            limit=limit,
            offset=offset,
        )
