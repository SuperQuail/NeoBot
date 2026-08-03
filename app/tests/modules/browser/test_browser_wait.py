from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neobot_app.browser.agent_browser.actions import AgentBrowser
from neobot_app.browser.agent_browser.manager import BrowserManager


class _Page:
    url = "https://example.test/current"


def _manager_with_page() -> BrowserManager:
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=_Page())
    manager.get_title = AsyncMock(return_value="Example")
    manager.get_text_length = AsyncMock(return_value=42)
    return manager


@pytest.mark.asyncio
async def test_browser_manager_wait_accepts_legacy_seconds_argument():
    manager = _manager_with_page()

    result = await manager.wait(0)

    assert result == {
        "success": True,
        "condition": "timeout",
        "value": "0.0",
        "title": "Example",
        "url": "https://example.test/current",
        "text_length": 42,
    }


@pytest.mark.asyncio
async def test_browser_manager_wait_reports_url_timeout():
    manager = _manager_with_page()

    result = await manager.wait("url", "never-matches", timeout=0)

    assert result["success"] is False
    assert result["error"] == "等待 URL 超时: never-matches"


@pytest.mark.asyncio
async def test_browser_manager_wait_rejects_unknown_condition():
    manager = _manager_with_page()

    result = await manager.wait("unsupported")

    assert result == {"success": False, "error": "未知等待条件: unsupported"}


@pytest.mark.asyncio
async def test_agent_browser_wait_preserves_structured_result():
    backend = AsyncMock()
    backend.wait.return_value = {
        "success": True,
        "condition": "timeout",
        "value": "0.0",
        "title": "Example",
    }
    browser = object.__new__(AgentBrowser)
    browser._manager = backend
    browser._started = True

    result = await browser.wait(0)

    backend.wait.assert_awaited_once_with(0, "", 20)
    assert result["success"] is True
    assert result["title"] == "Example"
    assert "timestamp" in result
