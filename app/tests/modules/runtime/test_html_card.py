"""spec(4) Part D / spec(5) 4.3：公共 HTML 卡片渲染器（多主题）。

本轮补充覆盖：
- 主题注册 API（注册 / 覆盖 / 注销 / 未知回落）与自包含校验；
- 每套主题的专属字体栈、内嵌字体组装进 RenderOptions.fonts；
- 内联 SVG 装饰 / 徽章 / data URI 的自包含性；
- 新块类型（stats / rows / grid / note / pager / slot / marker）下的转义不变量；
- 可信片段注入（插槽 / 标记）不破坏转义。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import loguru
import pytest

from neobot_app.runtime.html_card import (
    BUILTIN_THEMES,
    THEMES,
    EmbeddedFont,
    ThemeFont,
    ThemeRegistrationError,
    card_fonts,
    get_screenshots,
    get_theme,
    has_slot,
    inject_marker,
    inject_slot,
    register_theme,
    registered_themes,
    render_card_html,
    render_card_image,
    resolve_theme,
    set_screenshots,
    slot_placeholder,
    svg_data_uri,
    theme_css,
    theme_svg,
    theme_variables,
    unregister_theme,
)

#: 每套内置主题的专属字体栈特征（提法：常见字体用系统族名）
THEME_FONT_HINTS = {
    "default": ("system-ui", "sans-serif"),
    "bottle": ("Songti SC", "serif"),
    "game": ("monospace",),
    "fortune": ("Songti SC", "SimSun", "serif"),
}


class FakePort:
    def __init__(
        self,
        *,
        data: bytes = b"\x89PNG-data",
        error: Exception | None = None,
        first_call_error: Exception | None = None,
    ) -> None:
        self.data = data
        self.error = error
        self.first_call_error = first_call_error
        self.calls: list[dict[str, Any]] = []

    async def render(self, *, html: str, options: Any, base_url: str | None = None) -> Any:
        self.calls.append({"html": html, "options": options, "base_url": base_url})
        if self.error is not None:
            raise self.error
        if self.first_call_error is not None and len(self.calls) == 1:
            raise self.first_call_error
        from neobot_app.screenshot import ScreenshotResult

        return ScreenshotResult(self.data, "png", 720, 100, 720.0, 100.0, 1.0)


@pytest.fixture
def temp_theme():
    """注册一个临时主题并在用例结束后注销（主题注册是全局状态）。"""
    created: list[str] = []

    def _register(theme_id: str, **kwargs: Any):
        created.append(theme_id)
        return register_theme(theme_id, replace=True, **kwargs)

    yield _register
    for theme_id in created:
        unregister_theme(theme_id)


def _demo_blocks() -> list[dict[str, Any]]:
    return [
        {"kind": "heading", "text": "概况"},
        {"kind": "stats", "cols": 3, "items": [("在线状态", "在线", "ok"), ("延迟", "38 ms", "accent")]},
        {"kind": "kv", "title": "运行", "items": [("在线状态", "在线"), ("延迟", "38 ms")]},
        {"kind": "rows", "columns": ["名称", "状态"], "rows": [["demo", "运行中"]]},
        {"kind": "note", "text": "备注"},
    ]


# ── 自包含 ──


@pytest.mark.parametrize("theme", ["default", "bottle", "game", "fortune", None, "nope"])
def test_card_html_is_self_contained(theme: str | None) -> None:
    """无外链、无 JS、无外部请求（含内联 SVG 装饰与背景）。"""
    html = render_card_html(
        title="运行状态",
        subtitle="NeoBot 1.0.0",
        blocks=[
            *_demo_blocks(),
            {"kind": "grid", "cols": 2, "cells": [[{"kind": "kv", "items": [("a", "b")]}]]},
            {"kind": "pager", "page": 1, "pages": 3},
            {"kind": "slot", "name": "art"},
            {"kind": "marker", "text": "@@MG_ART@@"},
        ],
        footer="页脚",
        theme=theme or "default",
    )

    assert html.startswith("<!DOCTYPE html>")
    assert "<script" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html.lower()
    assert "@import" not in html
    assert "<iframe" not in html.lower()
    for marker in ("运行状态", "NeoBot 1.0.0", "概况", "在线状态", "demo", "页脚", "第 1/3 页"):
        assert marker in html


def test_svg_data_uri_encodes_namespace_so_no_external_url() -> None:
    """内联 SVG 转 data URI 后不产生 http 字面量（xmlns 也被百分号编码）。"""
    uri = svg_data_uri('<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>')

    assert uri.startswith('url("data:image/svg+xml,')
    assert "http://" not in uri
    assert "https://" not in uri
    assert "%3A%2F%2F" in uri  # :// 被编码，浏览器解码后仍是标准命名空间


# ── 主题与字体 ──


def test_builtin_themes_declare_variables_and_own_font_stack() -> None:
    assert set(BUILTIN_THEMES) == {"default", "bottle", "game", "fortune"}
    assert set(BUILTIN_THEMES) <= set(THEMES)
    for name in BUILTIN_THEMES:
        variables = THEMES[name]
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
        for hint in THEME_FONT_HINTS[name]:
            assert hint in variables["--card-font"], f"{name} 字体栈缺少 {hint}"


def test_theme_decorations_are_self_contained_svg() -> None:
    """每套内置主题都带内联 SVG 装饰 + 徽章，且不含外链 / 脚本。"""
    for name in BUILTIN_THEMES:
        spec = get_theme(name)
        assert spec.ornament.startswith("<svg"), f"{name} 缺少背景装饰"
        assert spec.emblem.startswith("<svg"), f"{name} 缺少徽章"
        html = render_card_html(title="x", theme=name)
        assert 'class="card-emblem"' in html
        assert spec.ornament.split(">", 1)[0] in html
        assert "http://" not in html and "https://" not in html


def test_theme_svg_assets_are_exposed_as_css_variables(temp_theme) -> None:
    temp_theme(
        "asset-theme",
        svg_assets={"star": '<svg viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'},
    )

    value = theme_svg("asset-theme", "star")
    assert value.startswith('url("data:image/svg+xml,')
    assert THEMES["asset-theme"]["--svg-star"] == value
    assert "--svg-star" in theme_variables("asset-theme")


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


def test_register_theme_makes_it_renderable(temp_theme) -> None:
    spec = temp_theme(
        "fancy",
        variables={"--accent": "#ff00aa", "--card-bg": "#101010"},
        font_stack=['"Songti SC"', "serif"],
        css=".card-title { letter-spacing: 0.3em; }",
        background="linear-gradient(180deg, #101010, #202020)",
        ornament='<svg class="nb-fancy" width="100%" height="100%"></svg>',
        emblem='<svg viewBox="0 0 8 8"><rect width="8" height="8"/></svg>',
    )

    assert spec.id == "fancy"
    assert "fancy" in registered_themes()
    assert resolve_theme("fancy") == "fancy"
    html = render_card_html(title="标题", theme="fancy")
    assert "#ff00aa" in html
    assert "letter-spacing: 0.3em" in html
    assert "linear-gradient(180deg, #101010, #202020)" in html
    assert "nb-fancy" in html
    assert '"Songti SC", serif' in html
    # 缺失的核心变量用 default 兜底（任何主题都能出图）
    assert spec.variables["--radius"]
    assert spec.variables["--card-border"]
    assert unregister_theme("fancy") is True
    assert resolve_theme("fancy") == "default"


def test_register_theme_rejects_duplicate_without_replace() -> None:
    with pytest.raises(ThemeRegistrationError):
        register_theme("default", variables={"--accent": "#fff"})
    assert unregister_theme("default") is False  # 内置主题不可注销
    assert get_theme("default").id == "default"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"css": ".card { background: url(https://evil.example/x.png); }"},
        {"background": "url(http://evil.example/x.png)"},
        {"variables": {"--accent": "red; @import 'x'"}},
        {"variables": {"not-a-variable": "x"}},
        {"font_stack": ["url(https://evil.example/f.woff2)"]},
        {"ornament": "<svg><script>alert(1)</script></svg>"},
        {"ornament": '<svg><image href="http://evil.example/x.png"/></svg>'},
        {"ornament": '<svg onload="alert(1)"></svg>'},
        {"emblem": "<svg><foreignObject></foreignObject></svg>"},
        {"svg_assets": {"bad name": "<svg></svg>"}},
    ],
)
def test_register_theme_enforces_self_contained_contract(temp_theme, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ThemeRegistrationError):
        temp_theme("bad-theme", **kwargs)


def test_register_theme_temp(tmp_path: Path, temp_theme) -> None:
    """内嵌字体的两种写法：embed_fonts= 与 fonts=（自动识别为字体文件）。"""
    font_file = tmp_path / "Fake.ttf"
    font_file.write_bytes(b"\x00\x01\x00\x00fake-font")

    by_kwarg = temp_theme(
        "embed-one",
        font_stack=['"Fake"', "monospace"],
        embed_fonts=[EmbeddedFont("Fake", font_file, "truetype", "400")],
    )
    assert [font.family for font in by_kwarg.embed_fonts] == ["Fake"]

    by_fonts = temp_theme(
        "embed-two",
        font_stack=['"Fake"', "monospace"],
        fonts=[ThemeFont("Fake", str(font_file), "truetype", "700", "normal")],
    )
    assert by_fonts.embed_fonts[0].weight == "700"
    assert by_fonts.fonts[0] == '"Fake"'


# ── 内嵌字体 -> RenderOptions.fonts ──


async def test_embedded_fonts_are_assembled_into_render_options(tmp_path: Path, temp_theme) -> None:
    font_file = tmp_path / "Pixel.ttf"
    font_file.write_bytes(b"\x00\x01\x00\x00pixel-font")
    temp_theme(
        "pixel",
        font_stack=['"Pixel"', "monospace"],
        embed_fonts=[EmbeddedFont("Pixel", font_file, "truetype", "400")],
    )

    html = render_card_html(title="像素", theme="pixel")
    faces = card_fonts(html)
    assert len(faces) == 1
    assert faces[0].family == "Pixel"
    assert faces[0].source == font_file
    assert faces[0].format == "truetype"

    port = FakePort()
    assert await render_card_image(html, screenshots=port) == b"\x89PNG-data"
    options = port.calls[0]["options"]
    assert [(font.family, font.format, font.weight) for font in options.fonts] == [
        ("Pixel", "truetype", "400")
    ]
    # 有内嵌字体时必须等字体就绪，否则可能截到回退字体的那一帧
    assert options.wait_for_fonts is True


async def test_embedded_font_bytes_are_inlined(tmp_path: Path, temp_theme) -> None:
    temp_theme("bytes-font", embed_fonts=[EmbeddedFont("Bytes", b"raw-font-bytes", "woff2")])

    html = render_card_html(title="x", theme="bytes-font")
    faces = card_fonts(html)
    assert [font.family for font in faces] == ["Bytes"]
    assert faces[0].source == b"raw-font-bytes"


async def test_missing_font_file_warns_and_keeps_rendering(tmp_path: Path, temp_theme) -> None:
    messages: list[str] = []
    sink = loguru.logger.add(messages.append, level="WARNING")
    try:
        temp_theme(
            "missing-font",
            font_stack=['"Ghost"', "monospace"],
            embed_fonts=[EmbeddedFont("Ghost", tmp_path / "nope.ttf", "truetype")],
        )
        html = render_card_html(title="x", theme="missing-font")
    finally:
        loguru.logger.remove(sink)

    assert card_fonts(html) == ()
    assert any("内嵌字体文件不存在" in str(item) for item in messages)
    port = FakePort()
    assert await render_card_image(html, screenshots=port) == b"\x89PNG-data"
    assert port.calls[0]["options"].wait_for_fonts is False  # 没有可用字体就不额外等待


def test_font_base_dir_resolves_relative_paths(tmp_path: Path, temp_theme) -> None:
    (tmp_path / "assets").mkdir()
    font_file = tmp_path / "assets" / "Rel.ttf"
    font_file.write_bytes(b"rel-font")

    spec = temp_theme(
        "rel-font",
        font_base_dir=tmp_path,
        embed_fonts=[EmbeddedFont("Rel", "assets/Rel.ttf", "truetype")],
    )
    assert Path(spec.embed_fonts[0].source) == font_file


# ── 转义不变量 ──


def test_card_html_escapes_user_content() -> None:
    html = render_card_html(
        title="<b>x</b>",
        subtitle='"><script>alert(1)</script>',
        blocks=[{"kind": "kv", "items": [("<i>", '"quoted" & text')]}],
        footer="<img src=x onerror=1>",
    )
    assert "<b>x</b>" not in html
    assert "<script" not in html.lower()
    assert "&lt;b&gt;" in html
    assert "&quot;quoted&quot; &amp; text" in html
    assert "&lt;img src=x onerror=1&gt;" in html


def test_card_html_escapes_every_new_block_kind() -> None:
    payload = "<script>alert(1)</script>"
    html = render_card_html(
        title=payload,
        blocks=[
            {"kind": "heading", "text": payload},
            {"kind": "stats", "title": payload, "items": [(payload, payload, "ok")]},
            {"kind": "kv", "title": payload, "items": [(payload, payload)]},
            {
                "kind": "rows",
                "title": payload,
                "columns": [payload, payload],
                "rows": [[payload, [payload, payload]]],
            },
            {"kind": "grid", "cols": 2, "cells": [[{"kind": "note", "text": payload}]]},
            {"kind": "pager", "page": 1, "pages": 2, "hint": payload},
            {"kind": "note", "text": payload},
        ],
    )
    assert "<script" not in html.lower()
    assert html.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 12


def test_cell_mapping_is_escaped_and_toned() -> None:
    html = render_card_html(
        title="x",
        blocks=[
            {
                "kind": "rows",
                "columns": ["状态", "说明"],
                "rows": [[{"text": "<b>运行中</b>", "tone": "ok"}, {"text": "用法", "mono": True}]],
            },
            {"kind": "kv", "items": [("权限", {"text": "所有人", "chip": True})]},
        ],
    )
    assert "<b>运行中</b>" not in html
    assert "&lt;b&gt;运行中&lt;/b&gt;" in html
    assert 'class="cell cell--ok"' in html
    assert "cell--mono" in html
    assert "cell--chip" in html


# ── 插槽 / 标记 ──


def test_slot_injection_keeps_user_text_escaped() -> None:
    user_text = '<img src=x onerror="alert(1)">'
    html = render_card_html(
        title="漂流瓶",
        blocks=[
            {"kind": "slot", "name": "avatar"},
            {"kind": "kv", "items": [("正文", user_text)]},
        ],
    )
    assert has_slot(html, "avatar")

    injected = inject_slot(html, "avatar", '<div class="trusted">可信片段</div>')

    assert '<div class="trusted">可信片段</div>' in injected
    assert "可信片段" not in html  # 注入前只有占位符
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in injected
    assert "<img" not in injected  # 用户文本仍然是转义后的文本节点
    assert injected.count('class="block block--slot card-slot"') == 1


def test_slot_injection_falls_back_into_body_when_placeholder_missing() -> None:
    html = render_card_html(title="x", blocks=[{"kind": "note", "text": "hi"}])
    injected = inject_slot(html, "missing", "<b>fragment</b>")

    assert "<b>fragment</b>" in injected
    assert injected.index("<b>fragment</b>") > injected.index('<section class="card-body">')


def test_invalid_slot_name_is_ignored_not_rendered() -> None:
    messages: list[str] = []
    sink = loguru.logger.add(messages.append, level="WARNING")
    try:
        html = render_card_html(title="x", blocks=[{"kind": "slot", "name": 'a" onclick="x'}])
        unchanged = inject_slot(html, 'a" onclick="x', "<b>x</b>")
    finally:
        loguru.logger.remove(sink)

    assert "data-slot=" not in html
    assert "<b>x</b>" not in unchanged
    assert any("非法插槽名" in str(item) for item in messages)


def test_marker_block_and_legacy_note_marker_injection() -> None:
    marker = "@@MG_ART@@"
    html = render_card_html(
        title="x",
        blocks=[{"kind": "marker", "text": marker}, {"kind": "kv", "items": [("a", "b")]}],
    )
    assert f'data-marker="{marker}"' in html
    injected = inject_marker(html, marker, '<svg class="art"></svg>')
    assert '<svg class="art"></svg>' in injected
    assert f">{marker}<" not in injected  # 标记文本节点已被可信片段替换

    # 既有漂流瓶写法：marker 放在 note 块文本里
    legacy = render_card_html(title="x", blocks=[{"kind": "note", "text": "@@MG_AVATAR@@"}])
    assert '<div class="note">@@MG_AVATAR@@</div>' in legacy
    injected_legacy = inject_marker(legacy, "@@MG_AVATAR@@", '<div class="mg-avatar-row"></div>')
    assert '<div class="mg-avatar-row"></div>' in injected_legacy
    assert "@@MG_AVATAR@@" not in injected_legacy


def test_invalid_marker_name_is_ignored() -> None:
    messages: list[str] = []
    sink = loguru.logger.add(messages.append, level="WARNING")
    try:
        html = render_card_html(title="x", blocks=[{"kind": "marker", "text": "<script>"}])
        injected = inject_marker(html, "<script>", "<b>x</b>")
    finally:
        loguru.logger.remove(sink)

    assert "data-marker=" not in html
    assert "<b>x</b>" not in injected
    assert any("非法标记名" in str(item) for item in messages)


def test_slot_placeholder_helper_matches_renderer_output() -> None:
    html = render_card_html(title="x", blocks=[{"kind": "slot", "name": "art"}])

    assert slot_placeholder("art") in html


# ── 截图端口 ──


async def test_render_card_image_clips_to_the_card_element() -> None:
    """裁剪到 <main class="card">：full_page 的画布下限是浏览器视口（实测约 1036x905），
    比卡片大得多，直接出图会在右侧与下方留一大片空白，发到聊天里很难看。"""
    port = FakePort()
    data = await render_card_image("<p>x</p>", screenshots=port, timeout=12.5)

    assert data == b"\x89PNG-data"
    options = port.calls[0]["options"]
    assert options.screenshot.mode == "element"
    assert options.screenshot.selector == "main.card"
    assert options.screenshot.format == "png"
    assert options.timeout == 12.5
    assert options.fonts == ()
    assert options.wait_for_fonts is False
    assert len(port.calls) == 1, "命中元素时不应再截一次整页"


async def test_render_card_image_falls_back_to_full_page_without_card_element() -> None:
    """调用方传了自定义 HTML（没有 main.card）时退回整页，保持「绝不外抛」的契约。"""
    from neobot_contracts.ports.screenshot import ScreenshotTargetNotFound

    port = FakePort(first_call_error=ScreenshotTargetNotFound("screenshot target not found"))
    data = await render_card_image("<p>x</p>", screenshots=port)

    assert data == b"\x89PNG-data"
    assert [call["options"].screenshot.mode for call in port.calls] == ["element", "full_page"]


async def test_render_card_image_survives_flaky_font_verification() -> None:
    """截图链路对个别内嵌字体的校验会抖动：字体校验失败要降级为「不等校验直接渲染」，
    字体仍由端口内联，绝不能因此丢图。"""
    from neobot_contracts.ports.screenshot import FontLoadError

    port = FakePort(first_call_error=FontLoadError("caller-provided fonts failed to load: Pixel"))
    fonts = (EmbeddedFont("Pixel", b"raw", "truetype").font_face(),)

    data = await render_card_image("<p>x</p>", screenshots=port, fonts=fonts)

    assert data == b"\x89PNG-data"
    assert len(port.calls) == 2
    assert port.calls[0]["options"].wait_for_fonts is True
    assert port.calls[1]["options"].wait_for_fonts is False
    # 字体仍然带在第二次请求里（只是不再等校验结果）
    assert [font.family for font in port.calls[1]["options"].fonts] == ["Pixel"]
    assert port.calls[1]["options"].screenshot.mode == "element"


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


def test_theme_css_is_available_for_documented_themes() -> None:
    assert "var(--accent)" in theme_css("game")
    assert theme_css("game") == get_theme("game").css


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__]))
