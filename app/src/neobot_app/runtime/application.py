from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.reply import ReplyOrchestrator
from neobot_app.core.file_server import FileServer, ExpirationConfig
from neobot_app.core.paths import get_data_dir
from neobot_app.runtime.connection_readiness import (
    ConnectionReadinessProbe,
    ConnectionState,
)

if TYPE_CHECKING:
    from neobot_app.audio import TTSService
    from neobot_app.emoji.service import EmojiService
    from neobot_contracts.ports.screenshot import ScreenshotPort

T = TypeVar("T")


class ConnectionTimeoutError(RuntimeError):
    """OneBot 连接等待超时。

    保留此类型仅为兼容既有调用方的 except 分支；启动流程已不再抛它 ——
    框架未连接是可恢复的运行状态，不是启动失败。
    """


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
        screenshots: "ScreenshotPort | None" = None,
        creator_image_service: Any = None,
        drawing_manager: Any = None,
        background_coros: list | None = None,
        self_heal_manager: Any = None,
        connection_probe: ConnectionReadinessProbe | None = None,
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
                get_data_dir(),
                file_server_port,
                file_server_host,
                expiration_config,
                file_server_public_url,
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
        if screenshots is None:
            from neobot_app.screenshot import UnavailableScreenshots

            screenshots = UnavailableScreenshots()
        self.screenshots: "ScreenshotPort" = screenshots
        self._creator_image_service = creator_image_service
        self._drawing_manager = drawing_manager
        self._background_coros = background_coros or []
        self._background_tasks: list[asyncio.Task] = []
        self._self_heal_manager = self_heal_manager
        # 连接就绪与否属于运行状态，不属于启动成败：探针为 None 表示该适配器
        # 不需要等待连接（如内嵌 local 适配器）。
        self._connection_probe = connection_probe
        self._connection_state: ConnectionState | None = None

    @property
    def connection_state(self) -> ConnectionState | None:
        """最近一次连接观察结论；尚未启动时为 None。"""
        return self._connection_state

    async def start(self) -> None:
        if self._started:
            return
        self._logger.info("NeoBot启动中")
        self._shutdown_event.clear()
        started: list[str] = []
        try:
            started.append("file_server")
            await self.file_server.start()
            if self.tts_service is not None:
                started.append("tts")
                await self.tts_service.initialize()
            self._logger.info("文件服务器启动完成")
            if self._plugin_runtime is not None:
                started.append("plugin")
                await self._plugin_runtime.load_registered()
                self._logger.info("插件加载完成")
            started.append("adapter")
            await self.adapter.start()
            if self._connection_probe is not None:
                # 连接状态只观察、不致命：反向 WebSocket 服务已在监听，框架随时
                # 可以连入，事件管线会在连上的那一刻自然开始工作。启动流程（以及
                # 面板等已启动组件）绝不因为「框架还没连上」而被回滚。
                self._connection_state = await self._connection_probe.observe()
                self._logger.info(self._connection_state.startup_log())
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
                started.append("emoji")
                await self._emoji_service.start()
                self._logger.info("表情包服务启动完成")
            if self._background_coros:
                started.append("background")
            for coro in self._background_coros:
                self._background_tasks.append(asyncio.create_task(coro))
                self._logger.debug(
                    f"后台任务已启动: {getattr(coro, '__name__', coro.__class__.__name__)}"
                )
            if self._browser_lifecycle_manager is not None:
                started.append("browser")
                await self._browser_lifecycle_manager.start()
                self._logger.info("浏览器生命周期管理器启动完成")
            started.append("event_ingress")
            self.event_ingress.start()
            if self._scheduled_task_manager is not None:
                started.append("scheduled_task_manager")
                await self._scheduled_task_manager.start()
            if self._markdown_image_converter is not None:
                started.append("markdown_image_converter")
                await self._markdown_image_converter.start()
            if self._report_service is not None:
                self._report_task = asyncio.create_task(self._run_report_loop())
                started.append("report_task")
            self._started = True
        except BaseException:
            deferred = await self._rollback_start(started)
            self._started = False
            if deferred is not None:
                raise deferred
            raise

    async def _rollback_start(self, started: list[str]) -> BaseException | None:
        """Rollback startup without letting one cleanup failure skip later resources."""
        steps: list[tuple[str, Callable[[], Any]]] = []
        if "report_task" in started:
            steps.append(("report task", self._cancel_report_task))
        if "event_ingress" in started:
            steps.append(("event ingress", self.event_ingress.stop))
        if "markdown_image_converter" in started:
            steps.append(
                ("markdown image converter", self._markdown_image_converter.stop)
            )

        # These managers own providers/agents created before start(), so they
        # must be closed even when no explicit start marker exists.
        if self._self_heal_manager is not None:
            steps.append(("self heal manager", self._self_heal_manager.shutdown))
        if self._problem_solver_manager is not None:
            steps.append(
                ("problem solver manager", self._problem_solver_manager.shutdown)
            )
        if self._reply_orchestrator is not None:
            steps.append(("reply orchestrator", self._reply_orchestrator.shutdown))
        elif "scheduled_task_manager" in started:
            steps.append(
                ("scheduled task manager", self._scheduled_task_manager.shutdown)
            )
        if self._reply_orchestrator is None and self._drawing_manager is not None:
            steps.append(("drawing manager", self._drawing_manager.shutdown))
        if self._creator_image_service is not None:
            steps.append(("creator image service", self._creator_image_service.close))

        if "browser" in started and self._browser_lifecycle_manager is not None:
            steps.append(
                ("browser lifecycle manager", self._browser_lifecycle_manager.stop)
            )
        if self._browser_instance is not None:
            steps.append(("browser instance", self._browser_instance.close))
            steps.append(("browser artifacts", self._cleanup_browser_artifacts))
        if "background" in started or self._background_tasks:
            steps.append(("background tasks", self._cancel_background_tasks))
        if "emoji" in started and self._emoji_service is not None:
            steps.append(("emoji service", self._emoji_service.stop))
        if "plugin" in started and self._plugin_runtime is not None:
            steps.append(("plugin runtime", self._plugin_runtime.stop_all))

        # Registry closure follows reply/session cancellation so in-flight
        # delegate calls observe cancellation rather than a synthetic result.
        if self._plugin_runtime is not None:
            steps.append(("agent registry", self._close_agent_registry))
        if "adapter" in started:
            steps.append(("adapter", self._stop_adapter_with_timeout))
        if "tts" in started and self.tts_service is not None:
            steps.append(("tts service", self.tts_service.close))
        if self._archive_summary_service is not None:
            steps.append(
                ("archive summary service", self._archive_summary_service.close)
            )
        if self._vision_provider is not None:
            steps.append(("vision provider", self._vision_provider.close))
        if "file_server" in started:
            steps.append(("file server", self.file_server.stop))
        if self._engine is not None:
            steps.append(("database engine", self._engine.dispose))

        deferred = await self._run_cleanup_steps("startup rollback", steps)
        self._logger.warning("NeoBot启动失败，已回滚已启动的组件")
        return deferred

    async def _run_cleanup_steps(
        self,
        phase: str,
        steps: list[tuple[str, Callable[[], Any]]],
    ) -> BaseException | None:
        """Run all cleanup steps, shielding each from caller cancellation."""
        deferred: BaseException | None = None
        for label, action in steps:
            candidate = await self._run_cleanup_step(phase, label, action)
            if candidate is None:
                continue
            if deferred is None or isinstance(
                candidate, (KeyboardInterrupt, SystemExit)
            ):
                deferred = candidate
        return deferred

    async def _run_cleanup_step(
        self,
        phase: str,
        label: str,
        action: Callable[[], Any],
    ) -> BaseException | None:
        deferred_cancel: asyncio.CancelledError | None = None
        cleanup_task: asyncio.Future[Any] | None = None
        try:
            result = action()
            if inspect.isawaitable(result):
                cleanup_task = asyncio.ensure_future(result)
                while not cleanup_task.done():
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError as exc:
                        current = asyncio.current_task()
                        if current is not None and current.cancelling():
                            deferred_cancel = deferred_cancel or exc
                            continue
                        raise
                cleanup_task.result()
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                self._logger.error(
                    f"{label} 在 {phase} 阶段被中断",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return exc
            if isinstance(exc, asyncio.CancelledError):
                self._logger.warning(
                    f"{label} 在 {phase} 阶段被取消",
                    error_type=type(exc).__name__,
                )
                current = asyncio.current_task()
                if deferred_cancel is not None:
                    return deferred_cancel
                if current is not None and current.cancelling():
                    return exc
                return None
            self._logger.warning(
                f"{label} 在 {phase} 阶段失败",
                error_type=type(exc).__name__,
                error=str(exc),
            )
        return deferred_cancel

    async def _cancel_report_task(self) -> None:
        task = self._report_task
        self._report_task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _cancel_background_tasks(self) -> None:
        tasks = list(self._background_tasks)
        self._background_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _close_agent_registry(self) -> None:
        registry = getattr(self._plugin_runtime, "agent_registry", None)
        if registry is not None:
            await registry.close()

    async def run_forever(self) -> None:
        """持续运行直到收到关闭信号，然后优雅停止。"""
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            self._logger.info("收到取消信号，正在关闭...")
        finally:
            await self.stop()

    def request_stop(self, *, clear_restart: bool = False) -> None:
        if clear_restart:
            self._restart_requested = False
        self._shutdown_event.set()

    @property
    def restart_requested(self) -> bool:
        return self._restart_requested

    def request_restart(self) -> None:
        """请求优雅关闭；CLI 在事件循环退出后以新进程重新启动。"""
        self._restart_requested = True
        self._shutdown_event.set()

    async def stop(self) -> None:
        if not self._started:
            return
        deferred: BaseException | None = None
        try:
            deferred = await self._stop_components()
        finally:
            self._started = False
            self._connection_state = None
            self._logger.info("NeoBot已停止")
        if deferred is not None:
            raise deferred

    async def _stop_components(self) -> BaseException | None:
        self._shutdown_event.set()
        steps: list[tuple[str, Callable[[], Any]]] = []
        if self._self_heal_manager is not None:
            steps.append(("self heal manager", self._self_heal_manager.shutdown))
        if self._problem_solver_manager is not None:
            steps.append(
                ("problem solver manager", self._problem_solver_manager.shutdown)
            )
        if self._report_task is not None:
            steps.append(("report task", self._cancel_report_task))

        steps.append(("event ingress", self.event_ingress.stop))
        if self._reply_orchestrator is not None:
            steps.append(("reply orchestrator", self._reply_orchestrator.shutdown))
        else:
            if self._scheduled_task_manager is not None:
                steps.append(
                    ("scheduled task manager", self._scheduled_task_manager.shutdown)
                )
            if self._drawing_manager is not None:
                steps.append(("drawing manager", self._drawing_manager.shutdown))
        if self._message_pipeline is not None:
            steps.append(
                (
                    "message pipeline summaries",
                    self._message_pipeline.flush_pending_summaries,
                )
            )
        if self._archive_summary_service is not None:
            steps.append(
                ("archive summary service", self._archive_summary_service.close)
            )
        if self._plugin_runtime is not None:
            steps.append(("plugin runtime", self._plugin_runtime.stop_all))
        if self._creator_image_service is not None:
            steps.append(("creator image service", self._creator_image_service.close))
        if self._markdown_image_converter is not None:
            steps.append(
                ("markdown image converter", self._markdown_image_converter.stop)
            )
        if self._emoji_service is not None:
            steps.append(("emoji service", self._emoji_service.stop))
        if self._background_tasks:
            steps.append(("background tasks", self._cancel_background_tasks))

        # Reply/session work is gone before the shared registry begins draining.
        if self._plugin_runtime is not None:
            steps.append(("agent registry", self._close_agent_registry))
        if self._browser_lifecycle_manager is not None:
            steps.append(
                ("browser lifecycle manager", self._browser_lifecycle_manager.stop)
            )
        if self._browser_instance is not None:
            steps.append(("browser instance", self._browser_instance.close))
            steps.append(("browser artifacts", self._cleanup_browser_artifacts))
        if self._vision_provider is not None:
            steps.append(("vision provider", self._vision_provider.close))
        steps.append(("adapter", self._stop_adapter_with_timeout))
        if self.tts_service is not None:
            steps.append(("tts service", self.tts_service.close))
        steps.append(("file server", self.file_server.stop))
        if self._engine is not None:
            steps.append(("database engine", self._engine.dispose))
        return await self._run_cleanup_steps("shutdown", steps)

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
        """仅对适配器清理设置超时上限；核心/记忆关闭不设超时。"""
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
                self._logger.warning("报告生成失败", error=str(exc))
                await asyncio.sleep(60)
