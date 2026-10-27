"""MarkdownImageConverter 测试：渲染超时、浏览器失败降级、pillowmd 回退路径、画布裁剪。"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from PIL import Image

from neobot_app.reply.markdown_image import MarkdownImageConverter, MarkdownImageError


def _make_converter(tmp_path: Path, **overrides) -> MarkdownImageConverter:
    return MarkdownImageConverter(output_dir=tmp_path, **overrides)


async def test_convert_rejects_empty_markdown():
    """空/纯空白 markdown 必须抛 MarkdownImageError 且不产生输出文件。"""
    converter = _make_converter(Path("unused-dir"))
    with pytest.raises(MarkdownImageError, match="不能为空"):
        await converter.convert("   \n  ")
    assert not converter._output_dir.exists()


async def test_convert_times_out_when_browser_hangs(tmp_path, monkeypatch):
    """浏览器渲染挂起超过 _RENDER_TIMEOUT_SECONDS 时必须抛 asyncio.TimeoutError。"""
    converter = _make_converter(tmp_path, browser_instance=object())
    monkeypatch.setattr(MarkdownImageConverter, "_RENDER_TIMEOUT_SECONDS", 0.05)

    async def _hang(markdown_text: str, filename: str) -> Path:
        await asyncio.Event().wait()
        return tmp_path / f"{filename}.png"

    monkeypatch.setattr(converter, "_render_with_browser", _hang)

    with pytest.raises(asyncio.TimeoutError):
        await converter.convert("# 标题")


async def test_convert_falls_back_to_pillowmd_when_browser_fails(tmp_path, monkeypatch):
    """浏览器渲染抛异常时降级 pillowmd，必须返回真实存在的 png 文件。"""
    converter = _make_converter(tmp_path, browser_instance=object())
    await converter.start()

    async def _boom(markdown_text: str, filename: str) -> Path:
        raise RuntimeError("browser boom")

    monkeypatch.setattr(converter, "_render_with_browser", _boom)

    try:
        result = await converter.convert("# 降级测试\n\n正文内容")
        assert result.exists()
        assert result.suffix == ".png"
        assert result.parent == tmp_path
    finally:
        await converter.stop()


async def test_convert_browser_success_returns_path(tmp_path, monkeypatch):
    """浏览器渲染成功时 convert 返回其输出路径（不做额外转换）。"""
    converter = _make_converter(tmp_path, browser_instance=object())
    expected = tmp_path / "custom.png"
    expected.write_bytes(b"fake")

    async def _fake_browser(markdown_text: str, filename: str) -> Path:
        return expected

    monkeypatch.setattr(converter, "_render_with_browser", _fake_browser)

    result = await converter.convert("# 标题", filename="custom")

    assert result == expected


async def test_convert_force_pillowmd_skips_browser(tmp_path, monkeypatch):
    """force_pillowmd=True 时必须跳过浏览器渲染，直接走 pillowmd。"""
    converter = _make_converter(tmp_path, browser_instance=object())
    await converter.start()
    browser_called = False

    async def _should_not_run(markdown_text: str, filename: str) -> Path:
        nonlocal browser_called
        browser_called = True
        return tmp_path / "x.png"

    monkeypatch.setattr(converter, "_render_with_browser", _should_not_run)

    try:
        result = await converter.convert("# 直接 pillowmd", force_pillowmd=True)
        assert browser_called is False
        assert result.exists()
    finally:
        await converter.stop()


def test_cleanup_expired_removes_only_old_files(tmp_path):
    """_cleanup_expired 只删除超过最大年龄的 png/jpg/html，保留新文件。"""
    converter = _make_converter(tmp_path)
    old = tmp_path / "old.png"
    new = tmp_path / "new.png"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    old_time = time.time() - converter._TMP_MAX_AGE_SECONDS - 10
    new_time = time.time()
    os.utime(old, (old_time, old_time))
    os.utime(new, (new_time, new_time))

    converter._cleanup_expired()

    assert not old.exists()
    assert new.exists()


# ── 画布裁剪：不得把浏览器视口高度当成内容高度（fix(10)） ────────


class _FakeBrowser:
    """最小浏览器替身，复刻真实语义：整页 scrollHeight 不会小于视口高度。

    真实 Chrome 里 document.documentElement.scrollHeight >= clientHeight 是 CSS
    规范行为，浏览器窗口固定 1280x800，因此「先量整页、再设视口」在短内容上
    必然得到 ~800px 高的画布（下方全是空白）。这个替身把这条语义显式建模出来，
    让回归用例不依赖真机浏览器也能复现/锁死该缺陷。
    """

    def __init__(self, *, content_height: int, window_height: int = 800, broken_element: bool = False) -> None:
        self._content_height = content_height
        self._viewport = (1280, window_height)
        self._broken_element = broken_element
        self.viewports: list[tuple[int, int]] = []
        self.scripts: list[str] = []

    async def save(self, *, html, path, options, base_url=None):
        from neobot_app.screenshot import ScreenshotResult, ScreenshotTargetNotFound

        # Element capture must be requested: viewport capture would retain its
        # probe/window height and fail these content-height regressions.
        assert options.screenshot.mode == "element"
        assert options.screenshot.selector == "article.markdown-body"
        assert options.screenshot.height == 320
        assert options.ready_script
        if self._broken_element:
            raise ScreenshotTargetNotFound("article missing")
        width = options.screenshot.width
        height = max(self._content_height, 200)
        self.viewports.append((width, height))
        self.scripts.append(options.ready_script)
        Image.new("RGB", (width, min(height, 8193)), "white").save(path, "PNG")
        return ScreenshotResult(b"", "png", width, height, width, height, 1)


def _converter_with_browser(tmp_path: Path, browser: _FakeBrowser) -> MarkdownImageConverter:
    browser._shot_dir = tmp_path / "shots"
    browser._shot_dir.mkdir(parents=True, exist_ok=True)
    return MarkdownImageConverter(output_dir=tmp_path, screenshots=browser)


async def test_short_markdown_canvas_is_not_window_height(tmp_path: Path) -> None:
    """短内容：画布只能等于内容高度（下限 200），绝不能是浏览器窗口高度 800。"""
    browser = _FakeBrowser(content_height=140)
    converter = _converter_with_browser(tmp_path, browser)

    path = await converter.convert("# 标题\n\n一行正文。")

    with Image.open(path) as image:
        assert image.size == (840, 200)
    # 截图前才会设成最终画布高度；测量阶段用的是探针高度
    assert browser.viewports[-1] == (840, 200)
    assert any("getBoundingClientRect" in script for script in browser.scripts)


async def test_medium_markdown_canvas_hugs_content(tmp_path: Path) -> None:
    """中等内容（小于窗口高度）：画布等于内容高度，而不是 800。"""
    browser = _FakeBrowser(content_height=560)
    converter = _converter_with_browser(tmp_path, browser)

    path = await converter.convert("# 标题\n\n" + "\n".join(f"- {i}" for i in range(20)))

    with Image.open(path) as image:
        assert image.size == (840, 560)
    assert browser.viewports[-1] == (840, 560)


async def test_tall_markdown_canvas_follows_content(tmp_path: Path) -> None:
    """超长内容：画布跟随内容高度（上限 8192），不被探针高度截断。"""
    browser = _FakeBrowser(content_height=1500)
    converter = _converter_with_browser(tmp_path, browser)

    path = await converter.convert("# 标题\n\n" + "\n".join(f"- {i}" for i in range(200)))

    with Image.open(path) as image:
        assert image.size == (840, 1500)


async def test_canvas_height_over_limit_is_explicit_error(tmp_path: Path) -> None:
    """异常超长内容明确报错，不能交付裁掉下半部分的图片。"""
    browser = _FakeBrowser(content_height=200_000)
    converter = _converter_with_browser(tmp_path, browser)

    with pytest.raises(MarkdownImageError, match="dimensions exceed limit"):
        await converter.convert("# 标题")
    assert not list(tmp_path.glob("*.png"))


async def test_pillow_fallback_used_when_element_missing(tmp_path: Path) -> None:
    """截图元素缺失时使用文字降级，不能交付空白整页。"""
    browser = _FakeBrowser(content_height=430, broken_element=True)
    converter = _converter_with_browser(tmp_path, browser)

    path = await converter.convert("# 标题\n\n正文")

    with Image.open(path) as image:
        assert image.width > 0 and image.height > 0
