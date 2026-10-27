import pytest
from PIL import Image

from neobot_app.browser.agent_browser.manager import BrowserManager, _find_chrome_binary
from neobot_app.reply.markdown_image import MarkdownImageConverter
from neobot_app.screenshot import (
    RenderOptions,
    ScreenshotError,
    ScreenshotOptions,
    ScreenshotService,
    _DirectManagerBackend,
)


@pytest.mark.browser
async def test_offline_math_and_readiness_restore_isolated_tab(tmp_path, monkeypatch, unused_tcp_port):
    browser_path = _find_chrome_binary()
    if not browser_path:
        pytest.skip("Chrome unavailable")
    manager = BrowserManager(
        headless=True,
        user_data_dir=tmp_path / "profile",
        browser_path=browser_path,
        port=unused_tcp_port,
    )
    try:
        await manager.start()
        open_page = manager._open_temporary_page

        async def offline_page():
            import asyncio

            original, temporary = await open_page()
            await asyncio.to_thread(temporary.run_cdp, "Network.enable")
            await asyncio.to_thread(temporary.run_cdp, "Network.setBlockedURLs", urls=["http://*", "https://*"])
            return original, temporary

        monkeypatch.setattr(manager, "_open_temporary_page", offline_page)
        original = manager.page
        tabs = list(original._browser.tab_ids)
        service = ScreenshotService(_DirectManagerBackend(manager))
        # A pending Promise must finish before capture; a rejected one must fail.
        result = await service.render(
            html="<div id='ready' style='width:100px;height:20px'>waiting</div>",
            options=RenderOptions(
                screenshot=ScreenshotOptions(mode="element", selector="#ready"),
                ready_script="return new Promise(resolve => setTimeout(() => {"
                "document.querySelector('#ready').style.height='123px'; resolve(true);}, 50))",
            ),
        )
        assert result.height == 123
        with pytest.raises(ScreenshotError):
            await service.render(
                html="<p>bad</p>",
                options=RenderOptions(
                    screenshot=ScreenshotOptions(),
                    ready_script="return Promise.reject(new Error('readiness failure'))",
                ),
            )

        observations = []
        capture = manager.capture

        async def inspect(options):
            import asyncio

            observations.append(
                await asyncio.to_thread(
                    manager.page.run_js,
                    """
                return {math: document.querySelectorAll('.katex').length,
                  errors: document.querySelectorAll('.katex-error').length,
                  fonts: Array.from(document.fonts).filter(f => f.status === 'error').length,
                  mathFonts: Array.from(document.fonts).filter(f => f.family.includes('KaTeX') && f.status === 'loaded').length,
                  overflow: Array.from(document.querySelectorAll('.katex-html')).some(e =>
                    e.getBoundingClientRect().right > document.querySelector('article').getBoundingClientRect().right),
                  rightPadding: Math.min(...Array.from(document.querySelectorAll('.katex-base')).map(e =>
                    document.querySelector('article').getBoundingClientRect().right - e.getBoundingClientRect().right)),
                  source: document.querySelector('article').textContent};
            """,
                )
            )
            return await capture(options)

        monkeypatch.setattr(manager, "capture", inspect)
        converter = MarkdownImageConverter(output_dir=tmp_path, screenshots=service)
        sample = (
            r"# 离线数学渲染"
            "\n\n中文与行内公式 $x^2+y^2=z^2$。\n\n"
            r"$$\frac{1}{1+\frac{1}{x}}$$"
            "\n\n"
            r"$$\int_0^\infty e^{-x^2}\,dx=\frac{\sqrt{\pi}}{2}$$"
            "\n\n"
            r"$$\begin{pmatrix}a&b\\c&d\end{pmatrix}$$"
            "\n\n"
            "$$" + r"\frac{a_1+b_1}{c_1}" * 35 + "$$\n\n"
            r"坏公式 $\frac{1}$ 仍显示源码。"
            "\n\n```python\nprint('代码')\n```"
        )
        path = await converter.convert(sample, filename="math-offline")
        assert observations[-1]["math"] == 5
        assert observations[-1]["errors"] == 1
        assert observations[-1]["fonts"] == 0
        assert observations[-1]["mathFonts"] > 0
        assert observations[-1]["overflow"] is False
        assert observations[-1]["rightPadding"] >= 23.5
        assert r"\frac{1}" in observations[-1]["source"]
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert 800 < image.width < 8192
            assert 200 < image.height < 8192
        normal = sample.replace("$$" + r"\frac{a_1+b_1}{c_1}" * 35 + "$$\n\n", "")
        normal_path = await converter.convert(normal, filename="math-normal")
        with Image.open(normal_path) as image:
            assert 800 <= image.width <= 840

        # Actual element sizes, including the old short-page blank-space bug.
        short = await converter.convert("一行 $x^2$", filename="short")
        medium = await converter.convert("正文\n\n" * 12, filename="medium")
        tall = await converter.convert("正文\n\n" * 80, filename="tall")
        with Image.open(short) as image:
            assert image.height == 200
        with Image.open(medium) as image:
            assert 200 < image.height < 800
        with Image.open(tall) as image:
            assert 1500 < image.height < 8192

        import asyncio

        other = MarkdownImageConverter(output_dir=tmp_path, screenshots=service)
        before = len(observations)
        first, second = await asyncio.gather(
            converter.convert("ONLY_FIRST $x^2$"),
            other.convert("ONLY_SECOND $y^2$"),
        )
        assert first != second
        assert first.exists() and second.exists()
        sources = [row["source"] for row in observations[before:]]
        assert len(sources) == 2
        assert sum("ONLY_FIRST" in text for text in sources) == 1
        assert sum("ONLY_SECOND" in text for text in sources) == 1
        assert not any("ONLY_FIRST" in text and "ONLY_SECOND" in text for text in sources)
        # Converter deadline covers the shared lock queue, before any tab opens.
        monkeypatch.setattr(other, "_RENDER_TIMEOUT_SECONDS", 0.03)
        async with service._backend.operation_lock:
            with pytest.raises(TimeoutError):
                await other.convert("queued", filename="queued")
        assert not (tmp_path / "queued.png").exists()
        assert manager.page is original
        assert list(original._browser.tab_ids) == tabs
    finally:
        await manager.close()
