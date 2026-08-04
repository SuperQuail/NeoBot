"""AgentBrowser 操作层生命周期与并发语义测试。

覆盖: _ensure 并发下只初始化一次、launch_headed 重建 manager 时参数保留
（browser_path 存在 BUG-001）、页面操作代理路径与异常包装。

全部用例以 unittest.mock 替代真实浏览器（BrowserManager/ChromiumPage），
不启动任何真实 Chrome 进程。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from neobot_app.browser.agent_browser import actions as actions_module
from neobot_app.browser.agent_browser import manager as manager_module
from neobot_app.browser.agent_browser.actions import AgentBrowser


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例前重置模块级实例注册表，保证用例间隔离。"""
    monkeypatch.setattr(manager_module, "_INSTANCE_REGISTRY", {})


class _FakeBrowserManager:
    """记录构造参数的最小假 manager，不启动任何真实浏览器。"""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self._port = kwargs.get("port", 0)
        self._operation_lock = kwargs.get("operation_lock")
        self._browser_path = kwargs.get("browser_path", "")
        self.user_data_dir = str(kwargs.get("user_data_dir", ""))

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def launch_headed(self, url: str | None = None) -> dict:
        return {"success": True, "mode": "headed", "url": url or "about:blank"}

    async def open(self, url: str = "") -> dict:
        return {"success": True, "action": "open", "url": url, "title": "Fake"}

    async def get_title(self) -> str:
        return "Fake Title"


@pytest.fixture()
def fake_manager_factory(monkeypatch: pytest.MonkeyPatch):
    """把 actions.BrowserManager 替换为记录型假 manager，并返回构造参数记录。"""
    created: list[dict] = []

    def factory(**kwargs) -> _FakeBrowserManager:
        created.append(kwargs)
        return _FakeBrowserManager(**kwargs)

    monkeypatch.setattr(actions_module, "BrowserManager", factory)
    return created


# ── _ensure 并发 ──


async def test_ensure_concurrent_calls_start_browser_once():
    """并发调用 _ensure 时，慢速 start 必须只执行一次，两个任务返回同一个 manager。"""
    agent = object.__new__(AgentBrowser)
    agent._started = False
    agent._manager = object()
    start_count = 0

    async def slow_start() -> None:
        nonlocal start_count
        start_count += 1
        await asyncio.sleep(0.02)
        agent._started = True

    agent.start = slow_start

    first, second = await asyncio.gather(agent._ensure(), agent._ensure())

    assert start_count == 1
    assert first is agent._manager
    assert second is agent._manager
    assert agent._started is True


# ── launch_headed ──


async def test_launch_headed_preserves_custom_browser_path(fake_manager_factory, tmp_path):
    """launch_headed 重建 manager 时必须保留原 browser_path，不得回退到默认查找。"""
    agent = AgentBrowser(
        user_data_dir=str(tmp_path / "data"),
        browser_path="C:/custom/chrome.exe",
    )

    result = await agent.launch_headed()

    assert result["success"] is True
    assert fake_manager_factory[-1].get("browser_path") == "C:/custom/chrome.exe"


async def test_launch_headed_rebuilds_manager_with_headed_mode(fake_manager_factory, tmp_path):
    """launch_headed 必须以 headless=False 重建 manager，保留 port 与 user_data_dir。"""
    agent = AgentBrowser(
        user_data_dir=str(tmp_path / "data"),
        browser_path="C:/custom/chrome.exe",
    )

    result = await agent.launch_headed("https://example.test/login")

    assert result["success"] is True
    assert result["mode"] == "headed"
    assert result["url"] == "https://example.test/login"
    assert fake_manager_factory[-1]["headless"] is False
    assert fake_manager_factory[-1]["port"] == 0
    assert fake_manager_factory[-1]["user_data_dir"] == str(tmp_path / "data")
    assert agent._started is True


# ── 页面操作代理路径 ──


async def test_get_title_delegates_to_manager():
    """get_title 必须把 manager 返回值包装为带 success/timestamp 的结构化结果。"""
    mgr = MagicMock()
    mgr.get_title = AsyncMock(return_value="Example")
    agent = object.__new__(AgentBrowser)
    agent._manager = mgr
    agent._started = True

    result = await agent.get_title()

    assert result["success"] is True
    assert result["title"] == "Example"
    assert "timestamp" in result
    mgr.get_title.assert_awaited_once()


async def test_get_title_returns_error_result_on_manager_failure():
    """manager 抛异常时 get_title 必须返回 success=False 且携带错误信息。"""
    mgr = MagicMock()
    mgr.get_title = AsyncMock(side_effect=RuntimeError("boom"))
    agent = object.__new__(AgentBrowser)
    agent._manager = mgr
    agent._started = True

    result = await agent.get_title()

    assert result["success"] is False
    assert "boom" in result["error"]


async def test_close_resets_started_and_delegates():
    """close 必须透传给 manager.close 并把 _started 复位为 False。"""
    mgr = MagicMock()
    mgr.close = AsyncMock()
    agent = object.__new__(AgentBrowser)
    agent._manager = mgr
    agent._started = True

    await agent.close()

    assert agent._started is False
    mgr.close.assert_awaited_once()
