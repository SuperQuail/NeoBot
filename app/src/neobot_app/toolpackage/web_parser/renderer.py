"""Dynamic page renderer using Playwright.

Supports:
- Render JavaScript-heavy pages and capture as rendered HTML or full-page screenshot
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional


@dataclass
class RenderedPage:
    """Result of dynamic page rendering."""

    url: str
    html: str = ""
    screenshot_base64: str = ""
    screenshot_path: str = ""
    error: Optional[str] = None
    render_time_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.error is None


class DynamicRenderer:
    """Render dynamic pages using a Playwright browser."""

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 900,
        timeout: float = 30_000,
        wait_until: str = "networkidle",
    ) -> None:
        self._headless = headless
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._timeout = timeout
        self._wait_until = wait_until
        self._browser = None
        self._context = None

    async def start(self) -> None:
        """Launch browser. Call once before rendering."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright 未安装。请执行:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(viewport=self._viewport)

    async def stop(self) -> None:
        """Close browser and release resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw"):
            await self._pw.stop()

    async def render(
        self,
        url: str,
        *,
        screenshot: bool = True,
        screenshot_path: str = "",
        inject_stealth: bool = True,
    ) -> RenderedPage:
        """Render a page and optionally capture a screenshot."""
        import time

        if self._browser is None or self._context is None:
            return RenderedPage(url=url, error="浏览器未启动，请先调用 start()")

        t0 = time.perf_counter()
        page = await self._context.new_page()

        try:
            if inject_stealth:
                await self._inject_stealth(page)

            await page.goto(url, timeout=self._timeout, wait_until=self._wait_until)

            html = await page.content()

            screenshot_b64 = ""
            if screenshot:
                data = await page.screenshot(full_page=True)
                screenshot_b64 = base64.b64encode(data).decode("utf-8")
                if screenshot_path:
                    with open(screenshot_path, "wb") as f:
                        f.write(data)

            return RenderedPage(
                url=url,
                html=html,
                screenshot_base64=screenshot_b64,
                screenshot_path=screenshot_path,
                render_time_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return RenderedPage(
                url=url,
                error=str(e),
                render_time_ms=(time.perf_counter() - t0) * 1000,
            )
        finally:
            await page.close()

    async def render_as_image(self, url: str, save_path: str = "") -> RenderedPage:
        """Convenience: render page as screenshot only."""
        return await self.render(url, screenshot=True, screenshot_path=save_path)

    async def _inject_stealth(self, page) -> None:
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(parameters)
            );
        """)
