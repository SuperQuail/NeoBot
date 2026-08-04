"""BrowserAgentWrapper 生命周期与锁传递测试。

覆盖: _ensure 并发下只创建/启动一次 AgentBrowser、operation_lock 三层传递、
close 幂等、open 委托路径。

全部用例以 unittest.mock 替代真实浏览器（BrowserManager），
不启动任何真实 Chrome 进程。
"""
from __future__ import annotations

import asyncio

import pytest

from neobot_app.browser import BrowserAgentWrapper
from neobot_app.browser.agent_browser import actions as actions_module
from neobot_app.browser.agent_browser import manager as manager_module


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


async def test_wrapper_ensure_creates_single_agent_under_concurrency(
    fake_manager_factory, tmp_path
):
    """并发调用 wrapper 工具方法时，_init_lock 必须保证只创建一个 AgentBrowser。"""
    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "data")

    first, second = await asyncio.gather(wrapper.get_title(), wrapper.get_title())

    assert len(fake_manager_factory) == 1
    assert first["success"] is True
    assert second["success"] is True
    assert wrapper._agent is not None
    assert wrapper._agent._started is True


async def test_wrapper_operation_lock_propagates_to_manager(
    fake_manager_factory, tmp_path
):
    """wrapper 的 operation_lock 必须一路传递给 AgentBrowser 与 BrowserManager。"""
    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "data")

    await wrapper._ensure()

    assert wrapper.operation_lock is wrapper._agent.operation_lock
    assert wrapper._agent.operation_lock is wrapper._agent._manager._operation_lock


async def test_wrapper_close_is_idempotent(fake_manager_factory, tmp_path):
    """wrapper.close 在未启动/已关闭后必须安全返回，且关闭后 _agent 置空。"""
    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "data")

    assert await wrapper.close() == {"success": True, "action": "close"}

    await wrapper._ensure()
    await wrapper.close()

    assert wrapper._agent is None
    assert await wrapper.close() == {"success": True, "action": "close"}


async def test_wrapper_open_delegates_to_agent(fake_manager_factory, tmp_path):
    """wrapper.open 必须把 url 透传给 agent，并返回其结构化结果。"""
    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "data")

    result = await wrapper.open("https://example.test")

    assert result["success"] is True
    assert result["url"] == "https://example.test"
    assert result["title"] == "Fake"
