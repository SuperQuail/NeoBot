"""SandboxLock — 沙箱文件操作独占锁。

确保同一时间只有一个 agent 可以对沙箱进行写操作。
支持主持有者和临时持有者两种模式。
"""

from __future__ import annotations


class SandboxLock:
    """沙箱文件操作锁。

    主持有者 (owner) 拥有完整的沙箱写权限。
    临时持有者 (temp_owners) 只能访问 ``temp/{chat_flow_id}`` 子目录。
    """

    def __init__(self) -> None:
        self._owner: str | None = None
        self._temp_owners: dict[str, str] = {}  # pipeline_key -> chat_flow_id

    @property
    def is_occupied(self) -> bool:
        """沙箱是否被任何 agent 占用。"""
        return self._owner is not None

    @property
    def owner(self) -> str | None:
        """当前主持有者的 pipeline_key。"""
        return self._owner

    def acquire(self, pipeline_key: str) -> bool:
        """尝试获取沙箱主锁。

        Returns:
            True 表示成功获取，False 表示已被其他 agent 占用。
        """
        if self._owner is not None and self._owner != pipeline_key:
            return False
        self._owner = pipeline_key
        return True

    def release(self, pipeline_key: str) -> bool:
        """释放沙箱主锁。

        Returns:
            True 表示成功释放，False 表示当前并无此持有者。
        """
        if self._owner != pipeline_key:
            return False
        self._owner = None
        return True

    def is_owner(self, pipeline_key: str) -> bool:
        """检查指定的 pipeline_key 是否为主持有者。"""
        return self._owner == pipeline_key

    def acquire_temp(self, pipeline_key: str, chat_flow_id: str) -> bool:
        """注册一个临时持有者。

        临时持有者不需要主锁，但限制只能操作 ``temp/{chat_flow_id}``。

        Returns:
            True 表示注册成功。
        """
        self._temp_owners[pipeline_key] = chat_flow_id
        return True

    def release_temp(self, pipeline_key: str) -> str | None:
        """释放临时持有者，返回其 chat_flow_id。"""
        return self._temp_owners.pop(pipeline_key, None)

    def get_temp_flow_id(self, pipeline_key: str) -> str | None:
        """获取临时持有者对应的 chat_flow_id。"""
        return self._temp_owners.get(pipeline_key)

    def is_temp_owner(self, pipeline_key: str) -> bool:
        """检查是否为临时持有者。"""
        return pipeline_key in self._temp_owners

    def clear(self) -> None:
        """清空所有锁状态。"""
        self._owner = None
        self._temp_owners.clear()
