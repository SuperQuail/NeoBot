from __future__ import annotations

import asyncio
import base64
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from neobot_app.browser.agent_browser.manager import BrowserManager
from neobot_app.screenshot import (
    FontFace,
    FontLoadError,
    InvalidScreenshotOptions,
    RenderOptions,
    ScreenshotError,
    ScreenshotOptions,
    ScreenshotResult,
    ScreenshotService,
    ScreenshotTargetNotFound,
    ScreenshotTimeout,
    ScreenshotUnavailable,
    UnavailableScreenshots,
    _font_css,
    validate_screenshot_options,
)


def _image_bytes(format: str = "PNG", size: tuple[int, int] = (20, 10)) -> bytes:
    output = BytesIO()
    Image.new("RGBA", size, (10, 20, 30, 255)).save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "options",
    [
        ScreenshotOptions(mode="element"),
        ScreenshotOptions(mode="viewport", selector="#card"),
        ScreenshotOptions(width=100),
        ScreenshotOptions(width=0, height=100),
        ScreenshotOptions(width=100, height=16385),
        ScreenshotOptions(scale=0.24),
        ScreenshotOptions(scale=4.01),
        ScreenshotOptions(quality=0),
        ScreenshotOptions(format="jpeg", transparent=True),
    ],
)
def test_screenshot_options_validation(options: ScreenshotOptions):
    with pytest.raises(InvalidScreenshotOptions):
        validate_screenshot_options(options)


def test_font_css_embeds_caller_data_and_default_font():
    css, families = _font_css(
        (FontFace('Neo "Sans"', b"font-data", weight="700"),), "Neo Sans"
    )

    assert families == ('Neo "Sans"',)
    assert "data:font/woff2;base64," + base64.b64encode(b"font-data").decode() in css
    assert 'font-family:"Neo \\"Sans\\""' in css
    assert "font-weight:700" in css
    assert 'html,body{font-family:"Neo Sans";}' in css


@pytest.mark.parametrize(
    "font",
    [
        FontFace("", b"font"),
        FontFace("Neo", b""),
        FontFace("Neo", Path("missing-font.woff2")),
        FontFace("Neo", b"font", format="invalid"),
        FontFace("Neo", b"font", weight="400; color:red"),
        FontFace("Neo", b"font", weight="normal 500"),
        FontFace("Neo", b"font", weight="900 100"),
        FontFace("Neo", b"font", style="normal; color:red"),
    ],
)
def test_font_validation_rejects_invalid_resources(font: FontFace):
    with pytest.raises(FontLoadError):
        _font_css((font,), None)


@pytest.mark.asyncio
async def test_browser_manager_capture_reports_image_and_css_metadata():
    image = _image_bytes(size=(20, 10))
    page = MagicMock()

    def run_js(script: str, *args):
        if "dpr:" in script:
            return '{"width":20,"height":10,"dpr":1,"x":0,"y":0}'
        return (
            '{"viewport":{"x":0,"y":0,"width":20,"height":10},'
            '"full":{"x":0,"y":0,"width":40,"height":30}}'
        )

    page.run_js.side_effect = run_js
    page.run_cdp.return_value = {"data": base64.b64encode(image).decode()}
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=page)
    manager._device_metrics_override = None

    result = await manager.capture(ScreenshotOptions())

    assert result.data == image
    assert (result.width, result.height) == (20, 10)
    assert (result.css_width, result.css_height, result.scale) == (20.0, 10.0, 1.0)
    assert page.run_cdp.call_args.args[0] == "Page.captureScreenshot"
    assert page.run_cdp.call_args.kwargs["format"] == "png"
    assert "quality" not in page.run_cdp.call_args.kwargs


@pytest.mark.asyncio
async def test_browser_manager_capture_restores_temporary_viewport_override():
    image = _image_bytes(size=(30, 15))
    page = MagicMock()
    page.run_js.side_effect = [
        '{"width":20,"height":10,"dpr":1,"x":0,"y":0}',
        (
            '{"viewport":{"x":0,"y":0,"width":30,"height":15},'
            '"full":{"x":0,"y":0,"width":30,"height":15}}'
        ),
    ]
    page.run_cdp.side_effect = [None, {"data": base64.b64encode(image).decode()}, None]
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=page)
    manager._device_metrics_override = None

    await manager.capture(ScreenshotOptions(width=30, height=15))

    assert page.run_cdp.call_args_list[-1].args[0] == "Emulation.clearDeviceMetricsOverride"


@pytest.mark.asyncio
async def test_open_temporary_page_cleans_up_when_activation_fails():
    browser = MagicMock()
    browser.tab_ids = ["original", "temporary"]
    browser.activate_tab.side_effect = [RuntimeError("activation failed"), None]
    original = MagicMock()
    original.tab_id = "original"
    original._browser = browser
    temporary = MagicMock()
    temporary.tab_id = "temporary"
    session = MagicMock()
    session.new_tab.return_value = temporary
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=original)
    manager._session_page = session
    manager._tab_pages = {}
    manager._page = original

    with pytest.raises(RuntimeError, match="activation failed"):
        await manager._open_temporary_page()

    original.run_cdp.assert_called_once_with(
        "Target.closeTarget", targetId="temporary"
    )
    assert browser.activate_tab.call_args_list[-1].args == ("original",)
    assert manager._page is original


class _TemporaryPage:
    def __init__(self, events: list[str] | None = None):
        self.events = events

    def run_cdp(self, method: str, **kwargs):
        if self.events is not None:
            self.events.append(method)
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "frame-1"}}}
        return None

    def run_js(self, script: str, *args):
        if "document.fonts.load" in script:
            return True
        return True


def _service_manager(
    original: object, temporary: _TemporaryPage, result: ScreenshotResult | None = None
):
    manager = MagicMock()
    manager._open_temporary_page = AsyncMock(return_value=(original, temporary))
    manager._apply_temporary_capture_metrics = AsyncMock(return_value=(temporary, False, None))
    manager._restore_temporary_capture_metrics = AsyncMock()
    manager._close_temporary_page = AsyncMock()
    if result is not None:
        manager.capture = AsyncMock(return_value=result)
    return manager


class _FakeBackend:
    """测试后端：包装 mock manager，提供真实 asyncio.Lock。"""

    def __init__(self, manager: object) -> None:
        self.manager = manager
        self.lock = asyncio.Lock()

    @property
    def operation_lock(self) -> asyncio.Lock:
        return self.lock

    async def get_manager(self):
        return self.manager


@pytest.mark.asyncio
async def test_service_closes_temporary_page_and_preserves_font_metadata():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(
        original,
        temporary,
        ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0),
    )
    service = ScreenshotService(_FakeBackend(manager))
    options = RenderOptions(
        screenshot=ScreenshotOptions(), fonts=(FontFace("Neo", b"font"),)
    )

    result = await service.render(
        html="<html><head></head><body>hello</body></html>",
        options=options,
        base_url="https://example.test/assets/",
    )

    assert result.fonts == ("Neo",)
    manager._close_temporary_page.assert_awaited_once_with(temporary, original)


@pytest.mark.asyncio
async def test_service_cleans_up_when_capture_fails():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(original, temporary)
    manager.capture = AsyncMock(side_effect=ScreenshotError("capture failed"))
    service = ScreenshotService(_FakeBackend(manager))

    with pytest.raises(ScreenshotError, match="capture failed"):
        await service.render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )

    manager._close_temporary_page.assert_awaited_once_with(temporary, original)


@pytest.mark.asyncio
async def test_service_timeout_still_closes_temporary_page():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(original, temporary)

    async def capture_forever(options: ScreenshotOptions):
        await asyncio.sleep(60)

    manager.capture = capture_forever
    service = ScreenshotService(_FakeBackend(manager))

    with pytest.raises(ScreenshotTimeout):
        await service.render(
            html="<p>hello</p>",
            options=RenderOptions(ScreenshotOptions(), timeout=0.01),
        )

    manager._close_temporary_page.assert_awaited_once_with(temporary, original)


@pytest.mark.asyncio
async def test_service_applies_metrics_before_loading_document():
    events: list[str] = []
    original = object()
    temporary = _TemporaryPage(events)
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)

    async def apply_metrics(options: ScreenshotOptions):
        events.append("apply-metrics")
        return temporary, False, None

    manager._apply_temporary_capture_metrics = apply_metrics

    await ScreenshotService(_FakeBackend(manager)).render(
        html="<picture><img srcset='small.png 1x, large.png 2x'></picture>",
        options=RenderOptions(ScreenshotOptions(width=600, height=400, scale=2)),
    )

    assert events.index("apply-metrics") < events.index("Page.setDocumentContent")


@pytest.mark.asyncio
async def test_service_reports_cleanup_failure_after_success():
    original = object()
    temporary = _TemporaryPage()
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)
    manager._close_temporary_page.side_effect = RuntimeError("close failed")

    with pytest.raises(ScreenshotError, match="restore browser state"):
        await ScreenshotService(_FakeBackend(manager)).render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )


@pytest.mark.asyncio
async def test_service_preserves_primary_error_when_cleanup_also_fails():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(original, temporary)
    manager.capture = AsyncMock(side_effect=ScreenshotError("capture failed"))
    manager._close_temporary_page.side_effect = RuntimeError("close failed")

    with pytest.raises(ScreenshotError, match="capture failed"):
        await ScreenshotService(_FakeBackend(manager)).render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )


@pytest.mark.asyncio
async def test_service_verifies_only_caller_fonts():
    original = object()
    temporary = _TemporaryPage()
    checked_specs: list[str] = []

    def run_js(script: str, *args):
        if "document.fonts.load" in script:
            checked_specs.append(args[0])
            return True
        return True

    temporary.run_js = run_js
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)
    options = RenderOptions(
        ScreenshotOptions(),
        fonts=(FontFace("Neo", b"font", weight="400 700", style="italic"),),
    )

    rendered = await ScreenshotService(_FakeBackend(manager)).render(
        html="<p>x</p>", options=options
    )

    assert checked_specs == ['italic 400 16px "Neo"']
    assert rendered.fonts == ("Neo",)


@pytest.mark.asyncio
async def test_service_holds_shared_lock_across_render():
    original = object()
    temporary = _TemporaryPage()
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)
    backend = _FakeBackend(manager)
    observed: list[bool] = []

    async def capture(options: ScreenshotOptions):
        observed.append(backend.lock.locked())
        return result

    manager.capture = capture

    await ScreenshotService(backend).render(
        html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
    )

    assert observed == [True]
    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_service_releases_lock_when_render_fails():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(original, temporary)
    manager.capture = AsyncMock(side_effect=ScreenshotError("capture failed"))
    backend = _FakeBackend(manager)

    with pytest.raises(ScreenshotError, match="capture failed"):
        await ScreenshotService(backend).render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )

    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_service_serializes_concurrent_renders_on_shared_lock():
    original = object()
    temporary = _TemporaryPage()
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)
    backend = _FakeBackend(manager)

    first_entered = asyncio.Event()
    release = asyncio.Event()
    captures: list[str] = []

    async def capture(options: ScreenshotOptions):
        captures.append("capture")
        first_entered.set()
        await release.wait()
        return result

    manager.capture = capture
    service = ScreenshotService(backend)

    first = asyncio.create_task(
        service.render(html="<p>1</p>", options=RenderOptions(ScreenshotOptions()))
    )
    await first_entered.wait()
    second = asyncio.create_task(
        service.render(html="<p>2</p>", options=RenderOptions(ScreenshotOptions()))
    )
    await asyncio.sleep(0.05)
    assert captures == ["capture"]

    release.set()
    await asyncio.gather(first, second)

    assert captures == ["capture", "capture"]
    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_save_validates_extension_and_writes_atomically(tmp_path: Path):
    service = ScreenshotService(MagicMock())
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    service.render = AsyncMock(return_value=result)
    options = RenderOptions(ScreenshotOptions(format="png"))

    with pytest.raises(InvalidScreenshotOptions):
        await service.save(html="", path=tmp_path / "bad.jpg", options=options)

    target = tmp_path / "nested" / "shot.png"
    saved = await service.save(html="<p>hello</p>", path=target, options=options)

    assert target.read_bytes() == result.data
    assert saved.path == target


@pytest.mark.asyncio
async def test_unavailable_screenshots_raise_on_render_and_save():
    screenshots = UnavailableScreenshots()

    with pytest.raises(ScreenshotUnavailable, match="浏览器未启用或 Chromium 不可用"):
        await screenshots.render(
            html="<p>x</p>", options=RenderOptions(ScreenshotOptions())
        )
    with pytest.raises(ScreenshotUnavailable, match="浏览器未启用或 Chromium 不可用"):
        await screenshots.save(
            html="<p>x</p>", path="out.png", options=RenderOptions(ScreenshotOptions())
        )


def test_unavailable_screenshots_and_service_implement_screenshot_port():
    from neobot_app.screenshot import ScreenshotPort

    assert isinstance(UnavailableScreenshots(), ScreenshotPort)
    assert isinstance(ScreenshotService(MagicMock()), ScreenshotPort)
    assert issubclass(ScreenshotUnavailable, ScreenshotError)


def test_contracts_import_without_app_or_browser():
    contracts_src = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "src"
    script = (
        "import sys; sys.path.insert(0, "
        + repr(str(contracts_src))
        + ");"
        "import neobot_contracts.ports.screenshot as m;"
        "import neobot_contracts.ports as p;"
        "assert 'neobot_app' not in sys.modules;"
        "assert 'neobot_app.browser' not in sys.modules;"
        "assert p.ScreenshotPort is m.ScreenshotPort;"
        "assert m.FontFace and m.RenderOptions and m.ScreenshotResult;"
        "assert m.ScreenshotUnavailable and m.InvalidScreenshotOptions;"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_plugin_context_exposes_same_screenshots(tmp_path: Path):
    from neobot_modloader.context import RuntimePluginContext

    screenshots = object()
    ctx = RuntimePluginContext(
        plugin_name="test-plugin",
        plugin_dir=tmp_path,
        data_dir=tmp_path / "plugin-data",
        config=None,
        logger=None,
        adapter=object(),
        screenshots=screenshots,
    )
    assert ctx.screenshots is screenshots


def test_plugin_context_defaults_screenshots_to_none(tmp_path: Path):
    from neobot_modloader.context import RuntimePluginContext

    ctx = RuntimePluginContext(
        plugin_name="test-plugin",
        plugin_dir=tmp_path,
        data_dir=tmp_path / "plugin-data",
        config=None,
        logger=None,
        adapter=object(),
    )
    assert ctx.screenshots is None


def test_modloader_root_exports_screenshot_contracts():
    import neobot_modloader as modloader

    for name in (
        "FontFace",
        "FontFormat",
        "FontLoadError",
        "ImageFormat",
        "InvalidScreenshotOptions",
        "RenderOptions",
        "ScreenshotError",
        "ScreenshotMode",
        "ScreenshotOptions",
        "ScreenshotPort",
        "ScreenshotResult",
        "ScreenshotTargetNotFound",
        "ScreenshotTimeout",
        "ScreenshotUnavailable",
    ):
        assert name in modloader.__all__, name
        assert hasattr(modloader, name), name


def test_neobot_app_screenshot_reexports_contracts():
    import neobot_app.screenshot as screenshot_module
    import neobot_contracts.ports.screenshot as contracts_module

    for name in (
        "FontFace",
        "FontFormat",
        "FontLoadError",
        "ImageFormat",
        "InvalidScreenshotOptions",
        "RenderOptions",
        "ScreenshotError",
        "ScreenshotMode",
        "ScreenshotOptions",
        "ScreenshotPort",
        "ScreenshotResult",
        "ScreenshotTargetNotFound",
        "ScreenshotTimeout",
        "ScreenshotUnavailable",
    ):
        assert getattr(screenshot_module, name) is getattr(contracts_module, name)


class _NullLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def _browser_config(enabled: bool):
    from types import SimpleNamespace

    browser_cfg = SimpleNamespace(
        enabled=enabled,
        auto_close_idle_seconds=600,
        hold_max_minutes=0,
        headless=True,
        port=0,
        browser_path="",
    )
    return SimpleNamespace(agent=SimpleNamespace(browser=browser_cfg))


def test_build_browser_components_disabled_yields_unavailable_screenshots(tmp_path):
    from neobot_app.bootstrap._runtime import build_browser_components
    from neobot_app.screenshot import UnavailableScreenshots

    result = build_browser_components(
        config=_browser_config(enabled=False),
        data_dir=tmp_path,
        logger=_NullLogger(),
    )

    assert result["browser_instance"] is None
    assert isinstance(result["screenshots"], UnavailableScreenshots)


def test_build_browser_components_enabled_yields_screenshot_service(tmp_path):
    from neobot_app.browser.agent_browser.manager import _find_chrome_binary
    from neobot_app.bootstrap._runtime import build_browser_components
    from neobot_app.screenshot import ScreenshotService

    if not _find_chrome_binary():
        pytest.skip("Chrome/Chromium is not installed")

    result = build_browser_components(
        config=_browser_config(enabled=True),
        data_dir=tmp_path,
        logger=_NullLogger(),
    )

    assert result["browser_instance"] is not None
    assert isinstance(result["screenshots"], ScreenshotService)


# ── 修复回归测试 ──


@pytest.mark.asyncio
async def test_open_temporary_page_cleans_up_on_cancellation():
    """取消（py3.13 CancelledError）中断标签页激活时仍须关闭临时标签页并还原原页面。"""
    browser = MagicMock()
    browser.tab_ids = ["original", "temporary"]
    browser.activate_tab.side_effect = [asyncio.CancelledError(), None]
    original = MagicMock()
    original.tab_id = "original"
    original._browser = browser
    temporary = MagicMock()
    temporary.tab_id = "temporary"
    session = MagicMock()
    session.new_tab.return_value = temporary
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=original)
    manager._session_page = session
    manager._tab_pages = {}
    manager._page = original

    with pytest.raises(asyncio.CancelledError):
        await manager._open_temporary_page()

    original.run_cdp.assert_called_once_with(
        "Target.closeTarget", targetId="temporary"
    )
    assert browser.activate_tab.call_args_list[-1].args == ("original",)
    assert manager._page is original


@pytest.mark.asyncio
async def test_service_wraps_browser_startup_failure_as_unavailable():
    backend = _FakeBackend(None)
    backend.get_manager = AsyncMock(
        side_effect=FileNotFoundError("chrome.exe not found")
    )
    service = ScreenshotService(backend)

    with pytest.raises(ScreenshotUnavailable, match="not available"):
        await service.render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )

    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_service_wraps_generic_manager_failure_as_screenshot_error():
    backend = _FakeBackend(None)
    backend.get_manager = AsyncMock(side_effect=RuntimeError("boom"))
    service = ScreenshotService(backend)

    with pytest.raises(ScreenshotError, match="failed to acquire browser"):
        await service.render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )

    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_service_passes_screenshot_errors_from_manager_unwrapped():
    backend = _FakeBackend(None)
    backend.get_manager = AsyncMock(
        side_effect=ScreenshotUnavailable("browser disabled")
    )
    service = ScreenshotService(backend)

    with pytest.raises(ScreenshotUnavailable, match="browser disabled"):
        await service.render(
            html="<p>hello</p>", options=RenderOptions(ScreenshotOptions())
        )


@pytest.mark.asyncio
async def test_browser_screenshot_backend_refuses_after_wrapper_close(tmp_path):
    from neobot_app.browser import BrowserAgentWrapper, BrowserScreenshotBackend

    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "browser-profile")
    backend = BrowserScreenshotBackend(wrapper)
    await wrapper.close()

    ensure_called = False

    async def ensure_unexpected():
        nonlocal ensure_called
        ensure_called = True
        raise AssertionError("_ensure must not run after close")

    wrapper._ensure = ensure_unexpected

    with pytest.raises(ScreenshotUnavailable, match="closed"):
        await backend.get_manager()

    assert not ensure_called
    assert wrapper._agent is None


@pytest.mark.asyncio
async def test_wrapper_can_reopen_for_skills_after_close(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from neobot_app.browser import BrowserAgentWrapper, BrowserScreenshotBackend

    fake_agent = MagicMock()
    fake_agent._started = False
    fake_agent.start = AsyncMock()
    fake_agent.close = AsyncMock()
    fake_agent._manager = object()
    monkeypatch.setattr(
        "neobot_app.browser.AgentBrowser", lambda **kwargs: fake_agent
    )

    wrapper = BrowserAgentWrapper(data_dir=tmp_path / "browser-profile")
    backend = BrowserScreenshotBackend(wrapper)
    await wrapper.close()

    assert await wrapper._ensure() is fake_agent
    fake_agent.start.assert_awaited_once()
    assert await backend.get_manager() is fake_agent._manager


@pytest.mark.asyncio
async def test_service_releases_lock_when_render_times_out():
    original = object()
    temporary = _TemporaryPage()
    manager = _service_manager(original, temporary)

    async def capture_forever(options: ScreenshotOptions):
        await asyncio.sleep(60)

    manager.capture = capture_forever
    backend = _FakeBackend(manager)

    with pytest.raises(ScreenshotTimeout):
        await ScreenshotService(backend).render(
            html="<p>hello</p>",
            options=RenderOptions(ScreenshotOptions(), timeout=0.01),
        )

    assert not backend.lock.locked()


@pytest.mark.asyncio
async def test_capture_missing_element_raises_target_not_found():
    page = MagicMock()

    def run_js(script: str, *args):
        if "dpr:" in script:
            return '{"width":20,"height":10,"dpr":1,"x":0,"y":0}'
        if "full:" in script:
            return (
                '{"viewport":{"x":0,"y":0,"width":20,"height":10},'
                '"full":{"x":0,"y":0,"width":40,"height":30}}'
            )
        return None

    page.run_js.side_effect = run_js
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=page)
    manager._device_metrics_override = None

    with pytest.raises(ScreenshotTargetNotFound, match="not found"):
        await manager.capture(ScreenshotOptions(mode="element", selector="#nope"))

    assert page.run_cdp.call_count == 0


@pytest.mark.asyncio
async def test_capture_zero_area_element_raises_target_not_found():
    page = MagicMock()

    def run_js(script: str, *args):
        if "dpr:" in script:
            return '{"width":20,"height":10,"dpr":1,"x":0,"y":0}'
        if "full:" in script:
            return (
                '{"viewport":{"x":0,"y":0,"width":20,"height":10},'
                '"full":{"x":0,"y":0,"width":40,"height":30}}'
            )
        return '{"x":0,"y":0,"width":0,"height":0}'

    page.run_js.side_effect = run_js
    manager = object.__new__(BrowserManager)
    manager._ensure_page = AsyncMock(return_value=page)
    manager._device_metrics_override = None

    with pytest.raises(ScreenshotTargetNotFound, match="no visible area"):
        await manager.capture(ScreenshotOptions(mode="element", selector="#empty"))

    assert page.run_cdp.call_count == 0


@pytest.mark.parametrize("timeout", [0, -1, 0.0, True])
@pytest.mark.asyncio
async def test_service_rejects_non_positive_timeout(timeout):
    manager = _service_manager(object(), _TemporaryPage())
    service = ScreenshotService(_FakeBackend(manager))

    with pytest.raises(InvalidScreenshotOptions, match="timeout"):
        await service.render(
            html="<p>hello</p>",
            options=RenderOptions(ScreenshotOptions(), timeout=timeout),
        )


@pytest.mark.asyncio
async def test_service_font_load_failure_lists_caller_fonts():
    original = object()
    temporary = _TemporaryPage()

    def run_js(script: str, *args):
        if "document.fonts.load" in script:
            return False
        return True

    temporary.run_js = run_js
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    manager = _service_manager(original, temporary, result)

    with pytest.raises(FontLoadError, match="Neo"):
        await ScreenshotService(_FakeBackend(manager)).render(
            html="<p>x</p>",
            options=RenderOptions(
                ScreenshotOptions(), fonts=(FontFace("Neo", b"font"),)
            ),
        )


@pytest.mark.asyncio
async def test_save_cleans_temporary_file_when_replace_fails(tmp_path, monkeypatch):
    service = ScreenshotService(MagicMock())
    result = ScreenshotResult(_image_bytes(), "png", 20, 10, 20.0, 10.0, 1.0)
    service.render = AsyncMock(return_value=result)
    options = RenderOptions(ScreenshotOptions(format="png"))

    def failing_replace(src: str, dst: str):
        raise OSError("replace failed")

    monkeypatch.setattr("os.replace", failing_replace)
    target = tmp_path / "shot.png"

    with pytest.raises(OSError, match="replace failed"):
        await service.save(html="<p>x</p>", path=target, options=options)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_save_reports_invalid_format_before_extension_check(tmp_path):
    service = ScreenshotService(MagicMock())
    service.render = AsyncMock()
    options = RenderOptions(ScreenshotOptions(format="gif"))

    with pytest.raises(InvalidScreenshotOptions, match="unsupported image format: gif"):
        await service.save(html="", path=tmp_path / "out.gif", options=options)

    service.render.assert_not_called()
