from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from neobot_app.browser import BrowserAgentWrapper, BrowserScreenshotBackend
from neobot_app.browser.agent_browser.manager import (
    BrowserManager,
    _find_chrome_binary,
)
from neobot_app.screenshot import (
    RenderOptions,
    ScreenshotOptions,
    ScreenshotService,
    _DirectManagerBackend,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_browser_screenshot_size.py"
LEADERBOARD_FIXTURE = PROJECT_ROOT / "scripts" / "fixtures" / "leaderboard.html"


def _require_chrome() -> str:
    """返回 Chrome 可执行路径；CI 下缺失则失败，否则跳过。"""
    browser_path = _find_chrome_binary()
    if not browser_path:
        if os.environ.get("CI"):
            pytest.fail(
                "Chrome/Chromium is required in CI but was not found "
                f"(CHROME_PATH={os.environ.get('CHROME_PATH', '')!r})"
            )
        pytest.skip("Chrome/Chromium is not installed")
    return browser_path


def _load_render_leaderboard():
    spec = importlib.util.spec_from_file_location(
        "neobot_screenshot_verification", VERIFY_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load screenshot verification helper: {VERIFY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.render_leaderboard


@pytest.mark.browser
@pytest.mark.asyncio
async def test_screenshot_service_saves_exact_element_size_and_restores_tab(
    tmp_path: Path,
):
    browser_path = _require_chrome()

    render_leaderboard = _load_render_leaderboard()
    rendered_html, dynamic_height = render_leaderboard(LEADERBOARD_FIXTURE, 10)
    assert dynamic_height == 798

    manager = BrowserManager(
        headless=True,
        user_data_dir=tmp_path / "browser-profile",
        browser_path=browser_path,
    )
    try:
        await manager.start()
        original_page = manager.page
        original_tab_id = original_page.tab_id
        original_url = original_page.url
        original_tab_ids = list(original_page._browser.tab_ids)
        output_path = tmp_path / "leaderboard.png"

        result = await ScreenshotService(_DirectManagerBackend(manager)).save(
            html=rendered_html,
            path=output_path,
            options=RenderOptions(
                screenshot=ScreenshotOptions(
                    mode="element",
                    selector="body",
                    width=560,
                    height=dynamic_height,
                    scale=1,
                    format="png",
                )
            ),
        )

        assert result.path == output_path
        assert output_path.exists()
        assert (result.width, result.height) == (560, 798)
        assert (result.css_width, result.css_height) == (560.0, 798.0)
        with Image.open(output_path) as image:
            assert image.format == "PNG"
            assert image.size == (560, 798)

        assert manager.page is original_page
        assert manager.page.tab_id == original_tab_id
        assert manager.page.url == original_url
        assert list(manager.page._browser.tab_ids) == original_tab_ids
    finally:
        await manager.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_screenshot_facade_through_browser_agent_wrapper(tmp_path: Path):
    browser_path = _require_chrome()

    render_leaderboard = _load_render_leaderboard()
    rendered_html, dynamic_height = render_leaderboard(LEADERBOARD_FIXTURE, 10)
    assert dynamic_height == 798

    wrapper = BrowserAgentWrapper(
        data_dir=tmp_path / "browser-profile",
        headless=True,
        browser_path=browser_path,
    )
    facade = ScreenshotService(BrowserScreenshotBackend(wrapper))
    try:
        manager = (await wrapper._ensure())._manager
        original_page = manager.page
        original_tab_id = original_page.tab_id
        original_url = original_page.url
        original_tab_ids = list(original_page._browser.tab_ids)
        output_path = tmp_path / "facade-leaderboard.png"

        result = await facade.save(
            html=rendered_html,
            path=output_path,
            options=RenderOptions(
                screenshot=ScreenshotOptions(
                    mode="element",
                    selector="body",
                    width=560,
                    height=dynamic_height,
                    scale=1,
                    format="png",
                )
            ),
        )

        assert result.path == output_path
        assert output_path.exists()
        assert (result.width, result.height) == (560, 798)
        assert (result.css_width, result.css_height) == (560.0, 798.0)
        with Image.open(output_path) as image:
            assert image.format == "PNG"
            assert image.size == (560, 798)

        assert manager.page is original_page
        assert manager.page.tab_id == original_tab_id
        assert manager.page.url == original_url
        assert list(manager.page._browser.tab_ids) == original_tab_ids
    finally:
        await wrapper.close()
