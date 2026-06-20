from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.reply import ReplyOrchestrator
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
        event_ingress: Any,
        message_pipeline: Any = None,
        reply_orchestrator: ReplyOrchestrator | None = None,
        emoji_service: "EmojiService | None" = None,
        logger: Logger | None = None,
        file_server_port: int = 8765,
        file_server_host: str = "127.0.0.1",
        file_server_public_url: str | None = None,
        file_server_enabled: bool = True,
        expiration_config: ExpirationConfig | None = None,
        tts_service: "TTSService | None" = None,
        bot_detector: Any = None,
        scheduled_task_manager: Any = None,
        problem_solver_manager: Any = None,
        markdown_image_converter: Any = None,
        plugin_runtime: Any = None,
        report_service: Any = None,
        engine: Any = None,
        vision_provider: Any = None,
        archive_summary_service: Any = None,
        file_server: FileServer | None = None,
        notification_hub: Any = None,
        browser_lifecycle_manager: Any = None,
    ) -> None:
        self.adapter: T = adapter
        self.chat_stream = chat_stream
        self.event_ingress = event_ingress
        self._message_pipeline = message_pipeline
        self._reply_orchestrator = reply_orchestrator
        self._emoji_service = emoji_service
        self._logger = logger or NullLogger()
        self._shutdown_event = asyncio.Event()
        self._started = False
        if file_server is not None:
            self.file_server = file_server
        else:
            self.file_server = FileServer(
                get_data_dir(), file_server_port, file_server_host, expiration_config, file_server_public_url,
                enabled=file_server_enabled,
            )
        self.tts_service = tts_service
        if self.tts_service is not None:
            self.tts_service.bind_file_server(self.file_server)
        self._bot_detector = bot_detector
        self._scheduled_task_manager = scheduled_task_manager
        self._problem_solver_manager = problem_solver_manager
        self._markdown_image_converter = markdown_image_converter
        self._plugin_runtime = plugin_runtime
        self._report_service = report_service
        self._report_task: asyncio.Task | None = None
        self._engine = engine
        self._vision_provider = vision_provider
        self._archive_summary_service = archive_summary_service
        self._notification_hub = notification_hub
        self._browser_lifecycle_manager = browser_lifecycle_manager
        self._maintenance_reminder_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._started:
            return
        self._logger.info("NeoBot启动中")
        self._shutdown_event.clear()
        await self.file_server.start()
        if self.tts_service is not None:
            await self.tts_service.initialize()
        self._logger.info("文件服务器启动完成")
        if self._plugin_runtime is not None:
            await self._plugin_runtime.load_registered()
            self._logger.info("插件加载完成")
        await self.adapter.start()
        if getattr(self.adapter, "requires_connection_wait", True):
            connected = await asyncio.to_thread(self.adapter.wait_for_connection, 30)
            if not connected:
                if self._plugin_runtime is not None:
                    await self._plugin_runtime.stop_all()
                await self.file_server.stop()
                if self.tts_service is not None:
                    await self.tts_service.close()
                await self.adapter.stop()
                raise ConnectionTimeoutError(
                    "连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接"
                )
        else:
            http_url = getattr(self.adapter, "http_url", "")
            ws_url = getattr(self.adapter, "ws_url", "")
            if http_url:
                self._logger.info(f"本地适配器 HTTP 地址: {http_url}")
            if ws_url:
                self._logger.info(f"本地适配器 WebSocket 地址: {ws_url}")
        self._logger.info("NeoBot适配器启动完成")
        if self._bot_detector is not None:
            await self._bot_detector.refresh()
            self._logger.info("官方Bot检测范围已加载")
        if self._plugin_runtime is not None:
            await self._plugin_runtime.start_all()
            self._logger.info("插件系统启动完成")
        await self.chat_stream.initialize()
        self._logger.info("NeoBot聊天流初始化完成")
        if self._emoji_service is not None:
            await self._emoji_service.start()
            self._logger.info("表情包服务启动完成")
        if self._notification_hub is not None:
            self._maintenance_reminder_task = asyncio.create_task(
                self._run_maintenance_reminder_loop()
            )
            self._logger.info("沙箱维护提醒循环已启动（每3小时）")
        if self._browser_lifecycle_manager is not None:
            await self._browser_lifecycle_manager.start()
            self._logger.info("浏览器生命周期管理器启动完成")
        self.event_ingress.start()
        if self._scheduled_task_manager is not None:
            await self._scheduled_task_manager.start()
        if self._markdown_image_converter is not None:
            await self._markdown_image_converter.start()
        if self._report_service is not None:
            self._report_task = asyncio.create_task(self._run_report_loop())
        self._started = True

    async def run_forever(self) -> None:
        """Run until a shutdown signal is received, then stop gracefully."""
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            self._logger.info("收到取消信号，正在关闭...")
        finally:
            await self.stop()

    def request_stop(self) -> None:
        self._shutdown_event.set()

    async def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_event.set()
        if self._report_task is not None:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
        self.event_ingress.stop()
        if self._message_pipeline is not None:
            await self._message_pipeline.flush_pending_summaries()
        if self._archive_summary_service is not None:
            await self._archive_summary_service.close()
        if self._plugin_runtime is not None:
            await self._plugin_runtime.stop_all()
        if self._reply_orchestrator is not None:
            await self._reply_orchestrator.shutdown()
        elif self._scheduled_task_manager is not None:
            await self._scheduled_task_manager.shutdown()
        if self._problem_solver_manager is not None:
            await self._problem_solver_manager.shutdown()
        if self._markdown_image_converter is not None:
            await self._markdown_image_converter.stop()
        if self._emoji_service is not None:
            await self._emoji_service.stop()
        if self._maintenance_reminder_task is not None:
            self._maintenance_reminder_task.cancel()
            try:
                await self._maintenance_reminder_task
            except asyncio.CancelledError:
                pass
            self._maintenance_reminder_task = None
        if self._browser_lifecycle_manager is not None:
            await self._browser_lifecycle_manager.stop()
        if self._vision_provider is not None:
            await self._vision_provider.close()
        await self.adapter.stop()
        if self.tts_service is not None:
            await self.tts_service.close()
        await self.file_server.stop()
        if self._engine is not None:
            await self._engine.dispose()
        self._started = False
        self._logger.info("NeoBot已停止")

    async def _run_maintenance_reminder_loop(self) -> None:
        """每 3 小时发布一条沙箱维护提醒通知，提示 AI 检查并清理。"""
        await asyncio.sleep(60)  # 启动后延迟 1 分钟
        while True:
            try:
                if self._notification_hub is not None:
                    await self._notification_hub.publish(
                        source="maintenance_reminder",
                        kind="group",
                        conversation_id="admin",
                        content=(
                            "<新的必须回复内容>\n"
                            "这是一条沙箱维护提醒。\n\n"
                            "## 前置要求\n"
                            "**在清理前，必须先阅读 sandbox/文件存储.md 了解当前存储规范。**\n"
                            "如文件存储.md 不存在，使用 sandbox_manager__read_file 检查 sandbox/ 目录结构后，\n"
                            "参考以下默认规范自行创建：\n\n"
                            "### 默认存储规范\n"
                            "- `tools/` — 可复用的工具脚本、程序\n"
                            "- `docs/` — 文档、参考资料、说明文件\n"
                            "- `assets/` — 静态资源（图片、字体、模板等）\n"
                            "- `temp/` — 临时文件，按 chat_flow_id 分子目录，可随时清理\n"
                            "- `gift/` — 礼物文件，由 gift skill 管理，勿手动编辑\n"
                            "- 文件命名统一使用 snake_case，中文名保留原样\n"
                            "- 根目录只保留 文件存储.md、TODO.md 和持久化目录\n\n"
                            "## 清理流程\n"
                            "1. 调用 sandbox_maintenance__check_capacity 检查容量\n"
                            "2. 调用 sandbox_maintenance__scan_temp_files 检查临时文件\n"
                            "3. 调用 sandbox_maintenance__get_maintenance_status 查看状态\n"
                            "4. 根据 文件存储.md 规范自行清理（sandbox_manager__delete_file 等）\n"
                            "5. **完成后调用 file_storage__update_storage_doc 更新 文件存储.md**\n"
                            "</新的必须回复内容>"
                        ),
                        manager_name="maintenance_reminder",
                        metadata={"interval_hours": 3},
                    )
            except Exception:
                pass
            try:
                await asyncio.sleep(10800)  # 3 小时
            except asyncio.CancelledError:
                break

    async def _run_report_loop(self) -> None:
        while True:
            try:
                await self._report_service.generate_all_reports()
                await asyncio.sleep(1800)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning("report generation failed", error=str(exc))
                await asyncio.sleep(60)
