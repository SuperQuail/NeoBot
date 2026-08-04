"""MarkdownImageConverter 测试：渲染超时、浏览器失败降级、pillowmd 回退路径。"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

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
