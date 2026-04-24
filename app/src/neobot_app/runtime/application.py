from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Generic, TypeVar

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.core.file_server import FileServer, ExpirationConfig
from neobot_app.core.paths import get_data_dir

if TYPE_CHECKING:
    from neobot_app.audio import TTSService
    from neobot_app.emoji.service import EmojiService

T = TypeVar("T")


class ConnectionTimeoutError(RuntimeError):
    """OneBot 连接等待超时"""


class NeoBotApplication(Generic[T]):
    def __init__(
        self,
        adapter: T,
        chat_stream: ChatStreamManager,
        event_pipeline: EventPipeline,
        reply_orchestrator: ReplyOrchestrator | None = None,
        emoji_service: "EmojiService | None" = None,
        logger: Logger | None = None,
        file_server_port: int = 8765,
        file_server_host: str = "127.0.0.1",
        file_server_public_url: str | None = None,
        expiration_config: ExpirationConfig | None = None,
        tts_service: "TTSService | None" = None,
    ) -> None:
        self.adapter: T = adapter
        self.chat_stream = chat_stream
        self.event_pipeline = event_pipeline
        self._reply_orchestrator = reply_orchestrator
        self._emoji_service = emoji_service
        self._logger = logger or NullLogger()
        self._shutdown_event = asyncio.Event()
        self._started = False
        self.file_server = FileServer(
            get_data_dir(), file_server_port, file_server_host, expiration_config, file_server_public_url
        )
        self.tts_service = tts_service
        if self.tts_service is not None:
            self.tts_service.bind_file_server(self.file_server)

    async def start(self) -> None:
        if self._started:
            return
        self._logger.info("NeoBot启动中")
        self._shutdown_event.clear()
        await self.file_server.start()
        if self.tts_service is not None:
            await self.tts_service.initialize()
        self._logger.info("文件服务器启动完成")
        await self.adapter.start()
        connected = await asyncio.to_thread(self.adapter.wait_for_connection, 30)
        if not connected:
            await self.file_server.stop()
            if self.tts_service is not None:
                await self.tts_service.close()
            await self.adapter.stop()
            raise ConnectionTimeoutError(
                "连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接"
            )
        self._logger.info("NeoBot适配器启动完成")
        await self.chat_stream.initialize()
        self._logger.info("NeoBot聊天流初始化完成")
        if self._emoji_service is not None:
            await self._emoji_service.start()
            self._logger.info("表情包服务启动完成")
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
        if self._reply_orchestrator is not None:
            await self._reply_orchestrator.shutdown()
        if self._emoji_service is not None:
            await self._emoji_service.stop()
        await self.adapter.stop()
        if self.tts_service is not None:
            await self.tts_service.close()
        await self.file_server.stop()
        self._started = False
        self._logger.info("NeoBot已停止")
