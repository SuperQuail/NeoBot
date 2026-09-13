"""spec(4) Part D / spec(5) 4.3：公共 HTML 卡片渲染器（多主题）。"""

from __future__ import annotations

from typing import Any

import loguru
import pytest

from neobot_app.runtime.html_card import (
    THEMES,
    get_screenshots,
    render_card_html,
    render_card_image,
    resolve_theme,
    set_screenshots,
    theme_variables,
)


class FakePort:
    def __init__(self, *, data: bytes = b"\x89PNG-data", error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def render(self, *, html: str, options: Any, base_url: str | None = None) -> Any:
        self.calls.append({"html": html, "options": options, "base_url": base_url})
        if self.error is not None:
            raise self.error
        from neobot_app.screenshot import ScreenshotResult

        return ScreenshotResult(self.data, "png", 720, 100, 720.0, 100.0, 1.0)


def test_card_html_is_self_contained() -> None:
    """A59：无外链、无 JS、无外部请求。"""
    html = render_card_html(
        title="运行状态",
        subtitle="NeoBot 1.0.0",
        blocks=[
            {"kind": "heading", "text": "概况"},
            {"kind": "kv", "items": [("在线状态", "在线")]},
            {"kind": "rows", "columns": ["名称", "状态"], "rows": [["demo", "运行中"]]},
            {"kind": "note", "text": "备注"},
        ],
        footer="页脚",
    )

    assert html.startswith("<!DOCTYPE html>")
    assert "<script" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html.lower()
    assert "@import" not in html
    for marker in ("运行状态", "NeoBot 1.0.0", "概况", "在线状态", "demo", "页脚"):
        assert marker in html


def test_card_html_escapes_user_content() -> None:
    html = render_card_html(
        title="<b>x</b>",
        blocks=[{"kind": "kv", "items": [("<i>", '"quoted" & text')]}],
    )
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html
    assert "&quot;quoted&quot; &amp; text" in html


def test_all_builtin_themes_expose_required_variables() -> None:
    assert set(THEMES) == {"default", "bottle", "game", "fortune"}
    for name, variables in THEMES.items():
        for key in (
            "--card-bg",
            "--card-fg",
            "--card-muted",
            "--accent",
            "--radius",
            "--card-border",
            "--card-font",
        ):
            assert key in variables, f"{name} 缺少 {key}"
        html = render_card_html(title="x", theme=name)
        assert variables["--accent"] in html
        # 只用系统字体栈：不出现外部字体地址
        assert "url(" not in variables["--card-font"]


def test_unknown_theme_falls_back_to_default_with_warning() -> None:
    messages: list[str] = []
    sink = loguru.logger.add(messages.append, level="WARNING")
    try:
        assert resolve_theme("nope") == "default"
        html = render_card_html(title="x", theme="nope")
    finally:
        loguru.logger.remove(sink)
    assert THEMES["default"]["--accent"] in html
    assert any("未知卡片主题" in str(item) for item in messages)


def test_theme_variables_are_css_block() -> None:
    block = theme_variables("game")
    assert block.startswith(":root {")
    assert "--accent" in block


async def test_render_card_image_returns_bytes_and_uses_full_page_png() -> None:
    port = FakePort()
    data = await render_card_image("<p>x</p>", screenshots=port, timeout=12.5)

    assert data == b"\x89PNG-data"
    options = port.calls[0]["options"]
    assert options.screenshot.mode == "full_page"
    assert options.screenshot.format == "png"
    assert options.timeout == 12.5


async def test_render_card_image_returns_none_on_failure() -> None:
    port = FakePort(error=RuntimeError("browser is not available"))
    assert await render_card_image("<p>x</p>", screenshots=port) is None


async def test_render_card_image_returns_none_without_port() -> None:
    set_screenshots(None)
    try:
        assert get_screenshots() is None
        assert await render_card_image("<p>x</p>") is None
    finally:
        set_screenshots(None)


async def test_render_card_image_returns_none_when_no_data() -> None:
    port = FakePort(data=b"")
    assert await render_card_image("<p>x</p>", screenshots=port) is None


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__]))
