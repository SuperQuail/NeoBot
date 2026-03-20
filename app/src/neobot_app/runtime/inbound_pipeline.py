"""InboundPipeline — 消息入站处理管线

IncomingMessage
  -> MessagePersistence（持久化到 storage）
  -> MemoryRecall（召回相关记忆）
  -> ReplyDecision（概率判断是否回复）
  -> ChatCompletion（调用 chat 生成回复）
  -> OutboundDispatch（通过 BotGateway 发送）
"""

from __future__ import annotations

from neobot_contracts.models import IncomingMessage
from neobot_contracts.ports.gateway import BotGateway
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_memory import MemoryService


class InboundPipeline:
    """统一的消息入站处理管线"""

    def __init__(
        self,
        gateway: BotGateway,
        memory: MemoryService | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._gateway = gateway
        self._memory = memory
        self._logger = logger or NullLogger()

    async def handle(self, message: IncomingMessage) -> None:
        """处理一条入站消息"""
        self._logger.info(
            f"收到消息 [{message.conversation.kind}:{message.conversation.id}] "
            f"{message.sender_name}: {message.text[:80]}"
        )

        # 1. 记忆存储
        if self._memory:
            try:
                await self._memory.remember(
                    conversation_id=f"{message.conversation.kind}:{message.conversation.id}",
                    speaker_id=message.sender_id,
                    content=message.text,
                )
            except Exception as exc:
                self._logger.error(f"记忆存储失败: {exc}")

        # 2. TODO: 回复决策 + Chat 生成 + 发送
        # 这些步骤将在 chat 服务完善后实现
