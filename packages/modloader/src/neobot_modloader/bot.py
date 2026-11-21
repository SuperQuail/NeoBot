from __future__ import annotations

from typing import Any

from neobot_contracts.models import ConversationRef

from neobot_modloader.message import normalize_message_payload


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

        将消息对象归一化后交给适配器，保持返回值和异常原样。
        """
        return await self._adapter.send(conversation, normalize_message_payload(message))

    async def send_private(self, user_id: int | str, message: Any) -> Any:
        """将 *message* 发送到由 *user_id* 标识的私聊。

        user_id 可以是 OneBot 数字 QQ 号，也可以是官方通道的 openid 字符串；
        统一走 ConversationRef + 门面 send，由适配器按会话/通道选路。
        """
        return await self.send(ConversationRef(kind="private", id=str(user_id)), message)

    async def send_group(self, group_id: int | str, message: Any) -> Any:
        """将 *message* 发送到由 *group_id* 标识的群聊。

        group_id 可以是 OneBot 群号，也可以是官方通道的 openid 字符串。
        """
        return await self.send(ConversationRef(kind="group", id=str(group_id)), message)
