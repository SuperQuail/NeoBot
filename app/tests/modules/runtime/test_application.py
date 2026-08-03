from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_app.runtime.application import NeoBotApplication
from neobot_contracts.ports.logging import NullLogger


class _FakeFileServer:
    """记录 start/stop 调用的假文件服务器。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeChatStream:
    """记录 initialize 调用并可选地通知测试的假聊天流。"""

    def __init__(self, started: asyncio.Event | None = None) -> None:
        self.initialized = False
        self._started = started

    async def initialize(self) -> None:
        self.initialized = True
        if self._started is not None:
            self._started.set()


class _FakeIngress:
    """记录 start/stop 调用的事件入口。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeAdapter:
    """最小假适配器：跳过连接等待，记录 start/stop。"""

    requires_connection_wait = False
    http_url = ""
    ws_url = ""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeConsole:
    """记录 start/stop 调用的假内置控制台。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


def _make_app(
    adapter: _FakeAdapter | None = None,
    file_server: _FakeFileServer | None = None,
    chat_stream: _FakeChatStream | None = None,
    ingress: _FakeIngress | None = None,
    browser_instance=None,
    console_service: _FakeConsole | None = None,
) -> NeoBotApplication:
    """构造一个仅依赖 Fake 组件的 NeoBotApplication（不调用真实构造函数）。"""
    app = object.__new__(NeoBotApplication)
    app.adapter = adapter or _FakeAdapter()
    app.file_server = file_server or _FakeFileServer()
    app.chat_stream = chat_stream or _FakeChatStream()
    app.event_ingress = ingress or _FakeIngress()
    app._message_pipeline = None
    app._reply_orchestrator = None
    app._emoji_service = None
    app._logger = NullLogger()
    app._shutdown_event = asyncio.Event()
    app._restart_requested = False
    app._started = False
    app.tts_service = None
    app._bot_detector = None
    app._scheduled_task_manager = None
    app._problem_solver_manager = None
    app._markdown_image_converter = None
    app._plugin_runtime = None
    app._report_service = None
    app._report_task = None
    app._engine = None
    app._vision_provider = None
    app._archive_summary_service = None
    app._browser_lifecycle_manager = None
    app._browser_instance = browser_instance
    app._creator_image_service = None
    app._drawing_manager = None
    app._background_coros = []
    app._background_tasks = []
    app._self_heal_manager = None
    app._console_service = console_service
    return app


def test_restart_request_is_distinct_from_normal_stop() -> None:
    application = object.__new__(NeoBotApplication)
    application._shutdown_event = asyncio.Event()
    application._restart_requested = False

    application.request_restart()
    assert application.restart_requested is True
    assert application._shutdown_event.is_set()

    application.request_stop()
    assert application.restart_requested is False


@pytest.mark.asyncio
async def test_adapter_shutdown_has_timeout_fallback() -> None:
    class HangingAdapter:
        def __init__(self) -> None:
            self.cancelled = False

        async def stop(self) -> None:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    application = object.__new__(NeoBotApplication)
    application.adapter = HangingAdapter()
    application._logger = NullLogger()
    application._ADAPTER_STOP_TIMEOUT_SECONDS = 0.01

    await application._stop_adapter_with_timeout()

    assert application.adapter.cancelled is True


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    """未启动时 stop 为无操作；已启动后连续调用两次 stop，清理动作只执行一次。"""
    # Arrange
    app = _make_app()

    # Act
    await app.stop()
    await app.start()
    await app.stop()
    await app.stop()

    # Assert
    assert app.adapter.stop_calls == 1
    assert app.file_server.stop_calls == 1
    assert app.event_ingress.stop_calls == 1
    assert app._started is False


@pytest.mark.asyncio
async def test_stop_closes_browser_instance(tmp_path) -> None:
    """stop 时必须调用浏览器实例的 close，并清理其截图产物目录。"""
    # Arrange
    shot_dir = tmp_path / "user-data" / "screenshots"
    shot_dir.mkdir(parents=True)
    shot = shot_dir / "shot.jpg"
    shot.write_bytes(b"fake-image")
    browser = SimpleNamespace(
        close=AsyncMock(),
        user_data_dir=str(tmp_path / "user-data"),
    )
    app = _make_app(browser_instance=browser)

    # Act
    await app.start()
    await app.stop()

    # Assert
    browser.close.assert_awaited_once()
    assert not shot.exists()


@pytest.mark.asyncio
async def test_start_partial_failure_cleans_up_started_components() -> None:
    """start 中途失败时必须回滚已启动的组件并向上传播异常，避免资源泄漏。"""
    # Arrange
    adapter = _FakeAdapter()
    adapter.start = AsyncMock(side_effect=RuntimeError("adapter start failed"))
    app = _make_app(adapter=adapter)

    # Act
    with pytest.raises(RuntimeError, match="adapter start failed"):
        await app.start()

    # Assert
    assert app._started is False
    assert app.file_server.stop_calls == 1


@pytest.mark.asyncio
async def test_console_starts_early_even_when_adapter_fails() -> None:
    """内置控制台必须在启动早期就绪: 即使 adapter 连接失败, 控制台也应已启动 (用于排查)。"""
    # Arrange
    console = _FakeConsole()
    adapter = _FakeAdapter()
    adapter.start = AsyncMock(side_effect=RuntimeError("adapter start failed"))
    app = _make_app(adapter=adapter, console_service=console)

    # Act
    with pytest.raises(RuntimeError, match="adapter start failed"):
        await app.start()

    # Assert: 控制台已在 adapter 失败前启动; 回滚时应被停止
    assert console.start_calls == 1
    assert console.stop_calls == 1


@pytest.mark.asyncio
async def test_console_started_before_adapter_connection_wait() -> None:
    """adapter 连接等待 (超时) 期间控制台应已可访问。"""
    # Arrange
    console = _FakeConsole()
    adapter = _FakeAdapter()
    adapter.requires_connection_wait = True
    adapter.wait_for_connection = lambda _timeout: False  # 连接超时 (同步函数, to_thread 调用)
    app = _make_app(adapter=adapter, console_service=console)

    # Act
    with pytest.raises(Exception):
        await app.start()

    # Assert: 控制台先于连接等待启动, 失败回滚后停止
    assert console.start_calls == 1
    assert console.stop_calls == 1


@pytest.mark.asyncio
async def test_restart_requested_survives_graceful_shutdown() -> None:
    """request_restart 后 run_forever 正常退出且 restart_requested 保持 True；
    request_stop 路径则保持 False（供外部区分重建与普通停止）。"""
    # Arrange
    started = asyncio.Event()
    app = _make_app(chat_stream=_FakeChatStream(started))

    # Act
    task = asyncio.create_task(app.run_forever())
    await started.wait()
    app.request_restart()
    await task

    # Assert
    assert app.restart_requested is True
    assert app._started is False
    assert app.file_server.stop_calls == 1

    # Arrange（正常停止路径）
    started2 = asyncio.Event()
    app2 = _make_app(chat_stream=_FakeChatStream(started2))

    # Act
    task2 = asyncio.create_task(app2.run_forever())
    await started2.wait()
    app2.request_stop()
    await task2

    # Assert
    assert app2.restart_requested is False
    assert app2._started is False
