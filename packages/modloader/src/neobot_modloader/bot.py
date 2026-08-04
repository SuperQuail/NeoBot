from __future__ import annotations

from typing import Any

from neobot_contracts.models import ConversationRef


class Bot:
    """适配器包装类，对外提供稳定的消息发送 API。

    暴露 ``send``、``send_private`` 与 ``send_group``，对插件和依赖注入
    解析出的处理器隐藏适配器内部实现。
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def self_id(self) -> Any:
        """从适配器获取机器人自身的 ID。"""
        return getattr(self._adapter, "self_id", None)

    async def send(self, conversation: ConversationRef, message: Any) -> Any:
        """将 *message* 发送到 *conversation*。

        委托给 ``adapter.send(conversation, message)``。
        """
        return await self._adapter.send(conversation, message)

    async def send_private(self, user_id: int, message: Any) -> Any:
        """将 *message* 发送到由 *user_id* 标识的私聊。

        委托给 ``adapter.send_private_msg(user_id, message)``。
        """
        return await self._adapter.send_private_msg(user_id, message)

    async def send_group(self, group_id: int, message: Any) -> Any:
        """将 *message* 发送到由 *group_id* 标识的群聊。

        委托给 ``adapter.send_group_msg(group_id, message)``。
        """
        return await self._adapter.send_group_msg(group_id, message)
