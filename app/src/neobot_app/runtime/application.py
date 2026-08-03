from __future__ import annotations

import asyncio
from pathlib import Path
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
    _ADAPTER_STOP_TIMEOUT_SECONDS = 12.0

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
        browser_lifecycle_manager: Any = None,
        browser_instance: Any = None,
        creator_image_service: Any = None,
        drawing_manager: Any = None,
        background_coros: list | None = None,
        self_heal_manager: Any = None,
        console_service: Any = None,
    ) -> None:
        self.adapter: T = adapter
        self.chat_stream = chat_stream
        self.event_ingress = event_ingress
        self._message_pipeline = message_pipeline
        self._reply_orchestrator = reply_orchestrator
        self._emoji_service = emoji_service
        self._logger = logger or NullLogger()
        self._shutdown_event = asyncio.Event()
        self._restart_requested = False
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
        self._browser_lifecycle_manager = browser_lifecycle_manager
        self._browser_instance = browser_instance
        self._creator_image_service = creator_image_service
        self._drawing_manager = drawing_manager
        self._background_coros = background_coros or []
        self._background_tasks: list[asyncio.Task] = []
        self._self_heal_manager = self_heal_manager
        self._console_service = console_service
        if self._console_service is not None:
            self._console_service.bind_application(self)

    async def start(self) -> None:
        if self._started:
            return
        self._logger.info("NeoBot启动中")
        self._shutdown_event.clear()
        started: list[str] = []
        try:
            await self.file_server.start()
            started.append("file_server")
            if self.tts_service is not None:
                await self.tts_service.initialize()
                started.append("tts")
            self._logger.info("文件服务器启动完成")
            if self._plugin_runtime is not None:
                await self._plugin_runtime.load_registered()
                started.append("plugin")
                self._logger.info("插件加载完成")
            await self.adapter.start()
            started.append("adapter")
            if getattr(self.adapter, "requires_connection_wait", True):
                connected = await asyncio.to_thread(self.adapter.wait_for_connection, 30)
                if not connected:
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
                started.append("emoji")
                self._logger.info("表情包服务启动完成")
            for coro in self._background_coros:
                self._background_tasks.append(asyncio.create_task(coro))
                self._logger.debug(f"后台任务已启动: {getattr(coro, '__name__', coro.__class__.__name__)}")
            if self._background_tasks:
                started.append("background")
            if self._browser_lifecycle_manager is not None:
                await self._browser_lifecycle_manager.start()
                started.append("browser")
                self._logger.info("浏览器生命周期管理器启动完成")
            self.event_ingress.start()
            started.append("event_ingress")
            if self._scheduled_task_manager is not None:
                await self._scheduled_task_manager.start()
                started.append("scheduled_task_manager")
            if self._markdown_image_converter is not None:
                await self._markdown_image_converter.start()
                started.append("markdown_image_converter")
            if self._report_service is not None:
                self._report_task = asyncio.create_task(self._run_report_loop())
                started.append("report_task")
            self._started = True
            if self._console_service is not None:
                try:
                    await self._console_service.start()
                except Exception as exc:
                    self._logger.error("内置控制台启动失败", error=str(exc))
        except Exception:
            await self._rollback_start(started)
            raise

    async def _rollback_start(self, started: list[str]) -> None:
        """start 中途失败时逆序回滚已启动的组件；单个组件清理失败只记日志，不掩盖原始异常。"""
        if "report_task" in started and self._report_task is not None:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
            self._report_task = None
        if "event_ingress" in started:
            self.event_ingress.stop()
        if "markdown_image_converter" in started:
            try:
                await self._markdown_image_converter.stop()
            except Exception as exc:
                self._logger.warning("markdown image converter stop failed on rollback", error=str(exc))
        if "scheduled_task_manager" in started:
            try:
                await self._scheduled_task_manager.shutdown()
            except Exception as exc:
                self._logger.warning("scheduled task manager shutdown failed on rollback", error=str(exc))
        if "browser" in started:
            if self._browser_lifecycle_manager is not None:
                try:
                    await self._browser_lifecycle_manager.stop()
                except Exception as exc:
                    self._logger.warning("browser lifecycle manager stop failed on rollback", error=str(exc))
            if self._browser_instance is not None:
                try:
                    await self._browser_instance.close()
                except Exception as exc:
                    self._logger.warning("browser close failed on rollback", error=str(exc))
            self._cleanup_browser_artifacts()
        if "background" in started:
            for task in self._background_tasks:
                task.cancel()
            for task in self._background_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._background_tasks.clear()
        if "emoji" in started:
            try:
                await self._emoji_service.stop()
            except Exception as exc:
                self._logger.warning("emoji service stop failed on rollback", error=str(exc))
        if "plugin" in started:
            try:
                await self._plugin_runtime.stop_all()
            except Exception as exc:
                self._logger.warning("plugin runtime stop failed on rollback", error=str(exc))
        if "adapter" in started:
            await self._stop_adapter_with_timeout()
        if "tts" in started:
            try:
                await self.tts_service.close()
            except Exception as exc:
                self._logger.warning("tts close failed on rollback", error=str(exc))
        if "file_server" in started:
            try:
                await self.file_server.stop()
            except Exception as exc:
                self._logger.warning("file server stop failed on rollback", error=str(exc))
        self._logger.warning("NeoBot启动失败，已回滚已启动的组件")

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
        self._restart_requested = False
        self._shutdown_event.set()

    @property
    def restart_requested(self) -> bool:
        return self._restart_requested

    def request_restart(self) -> None:
        """Request a full in-process rebuild after graceful core shutdown."""
        self._restart_requested = True
        self._shutdown_event.set()

    async def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_event.set()
        if self._console_service is not None:
            await self._console_service.stop()
        # Shut down self-heal manager first: cancel any in-flight heal task
        # so it doesn't spawn LLM calls or notifications during teardown.
        if self._self_heal_manager is not None:
            try:
                await self._self_heal_manager.shutdown()
            except Exception as exc:
                self._logger.warning("self heal manager shutdown failed", error=str(exc))
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
        if self._drawing_manager is not None:
            try:
                await self._drawing_manager.shutdown()
            except Exception as exc:
                self._logger.warning("drawing manager shutdown failed", error=str(exc))
        if self._creator_image_service is not None:
            try:
                await self._creator_image_service.close()
            except Exception as exc:
                self._logger.warning("creator image service close failed", error=str(exc))
        if self._markdown_image_converter is not None:
            await self._markdown_image_converter.stop()
        if self._emoji_service is not None:
            await self._emoji_service.stop()
        for task in self._background_tasks:
            task.cancel()
        for task in self._background_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._background_tasks.clear()
        if self._browser_lifecycle_manager is not None:
            try:
                await self._browser_lifecycle_manager.stop()
            except Exception as exc:
                self._logger.warning("browser lifecycle manager stop failed", error=str(exc))
        if self._browser_instance is not None:
            try:
                await self._browser_instance.close()
            except Exception as exc:
                self._logger.warning("browser close failed", error=str(exc))
        self._cleanup_browser_artifacts()
        if self._vision_provider is not None:
            await self._vision_provider.close()
        await self._stop_adapter_with_timeout()
        if self.tts_service is not None:
            await self.tts_service.close()
        await self.file_server.stop()
        if self._engine is not None:
            await self._engine.dispose()
        self._started = False
        self._logger.info("NeoBot已停止")

    def _cleanup_browser_artifacts(self) -> None:
        """删除浏览器截图/录屏产物（screenshots/*.jpg|png、annotated_*.png、recording_*.gif）。"""
        browser = self._browser_instance
        if browser is None:
            return
        browser_dir = Path(getattr(browser, "user_data_dir", "") or "")
        if not browser_dir.is_dir():
            return
        shot_dir = browser_dir / "screenshots"
        if shot_dir.is_dir():
            for child in shot_dir.iterdir():
                if child.is_file() and child.suffix.lower() in (".jpg", ".png"):
                    try:
                        child.unlink()
                    except OSError:
                        pass
        for pattern in ("annotated_*.png", "recording_*.gif"):
            for child in browser_dir.glob(pattern):
                if child.is_file():
                    try:
                        child.unlink()
                    except OSError:
                        pass

    async def _stop_adapter_with_timeout(self) -> None:
        """Bound only adapter cleanup; core/memory shutdown remains unbounded."""
        try:
            await asyncio.wait_for(
                self.adapter.stop(),
                timeout=self._ADAPTER_STOP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self._logger.error(
                "适配器停止超时，已触发兜底并继续关闭",
                timeout_seconds=self._ADAPTER_STOP_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            self._logger.error(
                "适配器停止异常，已触发兜底并继续关闭",
                error=str(exc),
            )

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
