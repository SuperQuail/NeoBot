from __future__ import annotations

import asyncio
from typing import Generic, TypeVar

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.runtime.event_pipeline import EventPipeline

T = TypeVar("T")


class ConnectionTimeoutError(RuntimeError):
    """OneBot 连接等待超时"""


class NeoBotApplication(Generic[T]):
    def __init__(
        self,
        adapter: T,
        chat_stream: ChatStreamManager,
        event_pipeline: EventPipeline,
        logger: Logger | None = None,
    ) -> None:
        self.adapter: T = adapter
        self.chat_stream = chat_stream
        self.event_pipeline = event_pipeline
        self._logger = logger or NullLogger()
        self._shutdown_event = asyncio.Event()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._logger.info("NeoBot启动中")
        self._shutdown_event.clear()
        await self.adapter.start()
        connected = await asyncio.to_thread(self.adapter.wait_for_connection, 30)
        if not connected:
            await self.adapter.stop()
            raise ConnectionTimeoutError(
                "连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接"
            )
        self._logger.info("NeoBot适配器启动完成")
        await self.chat_stream.initialize()
        self._logger.info("NeoBot聊天流初始化完成")
        self.event_pipeline.start()
        self._started = True

    async def run_forever(self) -> None:
        await self.start()
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    def request_stop(self) -> None:
        self._shutdown_event.set()

    async def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_event.set()
        self.event_pipeline.stop()
        await self.adapter.stop()
        self._started = False
        self._logger.info("NeoBot已停止")
