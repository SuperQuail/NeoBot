"""渲染入口：可信片段注入、卡片 HTML 组装与截图渲染。"""

from __future__ import annotations

import base64
import html as html_module
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.screenshot import (
    FontFace,
    RenderOptions,
    ScreenshotOptions,
    ScreenshotPort,
)

from .base import (
    _CARD_SELECTOR,
    _MARKER_NAME,
    _SLOT_NAME,
    DEFAULT_WIDTH,
    FONT_META_NAME,
    THEME_SPECS,
    ThemeSpec,
)
from .blocks import _escape, _render_blocks
from .common_css import _COMMON_CSS
from .template import _TEMPLATE
from .theme_registry import card_fonts, resolve_theme, theme_variables

logger = get_module_logger("runtime.html_card")


def _font_manifest(spec: ThemeSpec) -> str:
    """把主题内嵌字体序列化成 meta 标签（render_card_image 再从 HTML 读回）。

    字体文件缺失不算错：跳过该字体并记 warning，渲染回落系统字体。
    """
    if not spec.embed_fonts:
        return ""
    entries: list[dict[str, str]] = []
    for font in spec.embed_fonts:
        entry = {
            "family": str(font.family),
            "format": str(font.format),
            "weight": str(font.weight),
            "style": str(font.style),
        }
        if isinstance(font.source, bytes):
            if not font.source:
                logger.warning(f"内嵌字体 {font.family!r} 字节为空，已跳过")
                continue
            entry["data"] = base64.b64encode(font.source).decode("ascii")
        else:
            path = Path(font.source)
            try:
                missing = not path.is_file()
            except OSError:  # pragma: no cover - 极端非法路径
                missing = True
            if missing:
                logger.warning(f"内嵌字体文件不存在，已回落系统字体: {path}")
                continue
            entry["path"] = str(path)
        entries.append(entry)
    if not entries:
        return ""
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return f'<meta name="{FONT_META_NAME}" content="{html_module.escape(payload, quote=True)}">'



# ----------------------------------------------------------------------
# 可信片段注入：插槽（slot）与标记（marker）
# ----------------------------------------------------------------------


def slot_placeholder(name: str) -> str:
    """插槽占位符 HTML（{"kind": "slot", "name": ...} 渲染出来的形态）。"""
    key = str(name or "").strip().lower()
    return f'<div class="block block--slot card-slot" data-slot="{key}"><!--slot:{key}--></div>'


def has_slot(html: str, name: str) -> bool:
    """卡片 HTML 里是否存在指定插槽占位符。"""
    return slot_placeholder(name) in str(html or "")


def inject_slot(html: str, name: str, fragment: str) -> str:
    """把**可信片段**注入插槽（片段由调用方保证不含任何用户输入）。

    用户可控文本必须先 escape → Markdown → URL 清洗，绝不带进标签或属性。
    找不到占位符时退化为插到卡片内容区开头（内容不会丢）。
    """
    key = str(name or "").strip().lower()
    if not _SLOT_NAME.fullmatch(key):
        logger.warning(f"非法插槽名，注入已跳过: {name!r}")
        return html
    placeholder = slot_placeholder(key)
    target = f'<div class="block block--slot card-slot" data-slot="{key}">{fragment}</div>'
    source = str(html or "")
    if placeholder in source:
        return source.replace(placeholder, target, 1)
    logger.warning(f"卡片没有插槽 {key!r}，片段已插到内容区开头")
    return source.replace(
        '<section class="card-body">', '<section class="card-body">' + target, 1
    )


def inject_marker(html: str, marker: str, fragment: str) -> str:
    """把**可信片段**注入标记位（兼容既有 @@MG_XXX@@ 约定）。

    依次尝试：marker 块 → 既有的 note 块（漂流瓶头像用法）→ 原样标记串 →
    插到内容区开头。marker 名只接受 @@大写字母数字下划线@@。
    """
    text = str(marker or "").strip()
    if not _MARKER_NAME.fullmatch(text):
        logger.warning(f"非法标记名，注入已跳过: {marker!r}")
        return html
    source = str(html or "")
    block_placeholder = (
        f'<div class="block block--marker card-marker" data-marker="{text}">{text}</div>'
    )
    if block_placeholder in source:
        return source.replace(
            block_placeholder,
            f'<div class="block block--marker card-marker" data-marker="{text}">{fragment}</div>',
            1,
        )
    note_placeholder = f'<div class="note">{text}</div>'
    if note_placeholder in source:
        return source.replace(note_placeholder, f'<div class="block">{fragment}</div>', 1)
    if text in source:
        return source.replace(text, fragment, 1)
    logger.warning(f"卡片没有标记 {text!r}，片段已插到内容区开头")
    return source.replace(
        '<section class="card-body">', '<section class="card-body">' + fragment, 1
    )


# ----------------------------------------------------------------------
# 渲染入口
# ----------------------------------------------------------------------


def render_card_html(
    *,
    title: str,
    subtitle: str = "",
    blocks: Iterable[Any] = (),
    footer: str = "",
    theme: str = "default",
    width: int = DEFAULT_WIDTH,
) -> str:
    """生成自包含 HTML 卡片（内联 CSS、无 JS、无外链）。

    DSL 示例::

        render_card_html(
            title="运行状态",
            subtitle="NeoBot v1.0.0",
            blocks=[
                {"kind": "heading", "text": "概况"},
                {"kind": "stats", "cols": 3, "items": [("在线状态", "在线", "ok")]},
                {"kind": "kv", "title": "运行", "items": [("延迟", "42 ms")]},
                {"kind": "rows", "columns": ["名称", "版本"], "rows": [["a", "1.0.0"]]},
                {"kind": "note", "text": "纯文本降级时信息等价"},
                {"kind": "grid", "cols": 2, "cells": [[{"kind": "kv", "items": []}]]},
                {"kind": "slot", "name": "art"},            # 可信片段插槽
                {"kind": "marker", "text": "@@MG_ART@@"},   # 可信片段标记
            ],
            footer="第 1 页",
            theme="default",
            width=720,
        )

    - 全部文本字段（title / subtitle / footer / 块的文本与单元格）先 escape 再进文本节点；
    - slot / marker 的名字受严格字符集校验，注入的片段由调用方保证不含用户输入。
    """
    safe_width = max(240, int(width or DEFAULT_WIDTH))
    theme_id = resolve_theme(theme)
    spec = THEME_SPECS[theme_id]
    body = _render_blocks(blocks)
    subtitle_html = f'<div class="card-subtitle">{_escape(subtitle)}</div>' if subtitle else ""
    footer_html = f'<footer class="card-footer">{_escape(footer)}</footer>' if footer else ""
    emblem_html = (
        f'<div class="card-emblem" aria-hidden="true">{spec.emblem}</div>'
        if spec.emblem
        else ""
    )
    return _TEMPLATE.format(
        title_text=_escape(title),
        title=_escape(title),
        subtitle=subtitle_html,
        emblem=emblem_html,
        decor=spec.ornament,
        footer=footer_html,
        body=body or '<div class="block block--empty"><span class="empty">暂无数据</span></div>',
        variables=theme_variables(theme_id),
        common=_COMMON_CSS,
        theme_css=spec.css,
        font_meta=_font_manifest(spec),
        width=safe_width,
    )


#: 模块级默认截图端口（组合根可用 set_screenshots 注入）。
_screenshots: ScreenshotPort | None = None


def set_screenshots(port: ScreenshotPort | None) -> None:
    """注入默认截图端口（None 表示不可用，渲染一律返回 None）。"""
    global _screenshots
    _screenshots = port


def get_screenshots() -> ScreenshotPort | None:
    return _screenshots


async def render_card_image(
    html: str,
    *,
    timeout: float = 20.0,
    screenshots: ScreenshotPort | None = None,
    fonts: Sequence[FontFace] | None = None,
) -> bytes | None:
    """把自包含 HTML 渲染为 PNG 字节；不可用 / 失败 / 超时一律返回 None。

    - 主题的内嵌字体从 HTML 的字体清单里读回（也可用 fonts= 显式指定）；
    - 有内嵌字体时 wait_for_fonts=True（等字形真正就绪，避免截到回退字体），
      没有内嵌字体时保持 False，不额外等待；
    - 截图链路对个别内嵌字体（实测中日韩 woff2）的「校验」会概率性失败，
      此时自动降级为「不等校验直接渲染」——字体仍然内联并生效，绝不因此丢图；
    - ScreenshotService.render 内部已持有共享 operation_lock，因此本函数与
      markdown→图片天然串行，不会产生 Chromium 并发。
    """
    port = screenshots if screenshots is not None else _screenshots
    if port is None:
        logger.warning("截图端口不可用，卡片渲染降级为纯文本")
        return None
    faces = tuple(card_fonts(html)) if fonts is None else tuple(fonts)
    wait = bool(faces)
    # 裁剪到卡片元素本身（render_card_html 固定输出 <main class="card">）：
    # full_page 的画布下限是浏览器视口（实测约 1036x905），比卡片大得多，
    # 直接出图会在右侧与下方留一大片空白，发到聊天里很难看。
    #
    # 逐级尝试（任何失败都降级，绝不外抛）：
    #   ① 元素 + 等字体 → ② 元素 + 不等字体 → ③ 整页 + 等字体 → ④ 整页 + 不等字体
    # ② 专门兜底「截图链路对个别内嵌字体（实测 CJK woff2）校验抖动」：
    # 字体本身已由端口以 data URI 注入并生效，只是不再等校验结果，出图好过不出图。
    # ③ 兜底调用方自定义 HTML（没有 main.card）的情形。
    attempts: list[tuple[str, str | None, bool]] = [("element", _CARD_SELECTOR, wait)]
    if wait:
        attempts.append(("element", _CARD_SELECTOR, False))
    attempts.append(("full_page", None, wait))
    if wait:
        attempts.append(("full_page", None, False))

    last_error: Exception | None = None
    for mode, selector, use_wait in attempts:
        options = RenderOptions(
            screenshot=(
                ScreenshotOptions(mode=mode, selector=selector, format="png")  # type: ignore[arg-type]
                if selector
                else ScreenshotOptions(mode=mode, format="png")  # type: ignore[arg-type]
            ),
            fonts=faces,
            wait_for_fonts=use_wait,
            wait_for_images=False,
            timeout=float(timeout),
        )
        try:
            result = await port.render(html=html, options=options)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        data = getattr(result, "data", None)
        if not data:
            logger.warning("卡片渲染未返回渲染数据，已降级")
            return None
        if last_error is not None:
            logger.warning(
                "卡片首次渲染失败，备用方案已成功",
                mode=mode,
                wait_for_fonts=use_wait,
                error_type=type(last_error).__name__,
                error=str(last_error),
            )
        return bytes(data)
    logger.warning(f"卡片渲染失败，已降级: {last_error}")
    return None

