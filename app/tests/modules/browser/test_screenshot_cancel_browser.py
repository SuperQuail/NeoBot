from __future__ import annotations

import asyncio

import pytest

from neobot_app.browser.agent_browser.manager import BrowserManager, _find_chrome_binary
from neobot_app.screenshot import (
    RenderOptions,
    ScreenshotOptions,
    ScreenshotService,
    _DirectManagerBackend,
)


@pytest.mark.browser
async def test_active_readiness_cancel_restores_tabs_and_next_render(tmp_path, unused_tcp_port):
    browser_path = _find_chrome_binary()
    if not browser_path:
        pytest.skip("Chrome unavailable")
    manager = BrowserManager(
        headless=True,
        user_data_dir=tmp_path / "profile",
        browser_path=browser_path,
        port=unused_tcp_port,
    )
    pending = None
    try:
        await manager.start()
        original = manager.page
        tabs = list(original._browser.tab_ids)
        service = ScreenshotService(_DirectManagerBackend(manager))
        pending = asyncio.create_task(
            service.render(
                html="<p>pending</p>",
                options=RenderOptions(
                    screenshot=ScreenshotOptions(),
                    ready_script="window.__activeReadiness = true; return new Promise("
                    "resolve => setTimeout(() => resolve(true), 2000));",
                    timeout=5,
                ),
            )
        )
        # Observe an actual running page script before cancellation. No sleep is
        # used to guess readiness; the marker is set inside the awaited script.
        async with asyncio.timeout(5):
            while True:
                if manager.page is not original:
                    active = await asyncio.to_thread(
                        manager.page.run_js,
                        "return window.__activeReadiness === true",
                        timeout=1,
                    )
                    if active:
                        break
                await asyncio.sleep(0)
        assert not pending.done()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert manager.page is original
        assert list(original._browser.tab_ids) == tabs
        assert not service._backend.operation_lock.locked()
        result = await service.render(
            html="<div style='width:140px;height:75px'>next</div>",
            options=RenderOptions(
                screenshot=ScreenshotOptions(mode="element", selector="div"),
                ready_script="return Promise.resolve(true)",
            ),
        )
        assert (result.width, result.height) == (140, 75)
        assert manager.page is original
        assert list(original._browser.tab_ids) == tabs
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await manager.close()
