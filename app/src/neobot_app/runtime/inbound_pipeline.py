"""规范化入站消息的入站管线。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_adapter.mapping import map_to_incoming_message
from neobot_contracts.models import IncomingMessage
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import MemoryService

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


class InboundPipeline:
    """规范化入站消息并持久化短期记忆。"""

    def __init__(
        self,
        adapter: OneBotAdapter,
        memory: MemoryService | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._memory = memory
        self._logger = logger or NullLogger()

    async def handle(self, message: IncomingMessage) -> None:
        # 入队明细由 message.enqueued 记录；接收摘要留 DEBUG，避免同一消息两条 INFO
        self._logger.debug(
            "收到消息",
            event="message.received",
            event_id=message.event_id,
            chat_flow_id=f"{message.conversation.kind}:{message.conversation.id}",
            conversation_kind=message.conversation.kind,
            conversation_id=message.conversation.id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            preview=message.text[:80],
        )

        # NOTE: 短期记忆（MemoryService.remember）为未完成功能。
        # 当前仅将消息写入内存列表，无任何检索调用方（recall 无使用者），
        # 且纯内存存储在重启后丢失，暂不启用。
        # if self._memory is None:
        #     return
        # try:
        #     await self._memory.remember(
        #         conversation_id=str(message.conversation.id),
        #         speaker_id=message.sender_id,
        #         content=message.text,
        #     )
        # except Exception as exc:
        #     self._logger.error("记忆存储失败", error=str(exc))

    async def handle_raw_event(self, raw_event: dict[str, Any]) -> None:
        await self.handle(map_to_incoming_message(raw_event))
