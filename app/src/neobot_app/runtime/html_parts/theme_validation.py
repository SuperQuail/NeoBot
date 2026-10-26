"""主题注册校验与资源归一化：自包含红线、字体栈、内嵌字体、SVG 资产。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from neobot_app.utils.logger import get_module_logger

from .base import (
    _EVENT_HANDLER,
    _FORBIDDEN_MARKUP,
    _FORBIDDEN_TEXT,
    EmbeddedFont,
    ThemeRegistrationError,
)

logger = get_module_logger("runtime.html_card")

def _forbid_unsafe_text(value: str, *, where: str) -> None:
    lowered = str(value).lower()
    for item in _FORBIDDEN_TEXT:
        if item in lowered:
            raise ThemeRegistrationError(
                f"{where} 违反自包含约束（出现 {item!r}）：主题不允许外链 / 脚本 / @import"
            )


def _forbid_unsafe_markup(markup: str, *, where: str) -> None:
    lowered = str(markup).lower()
    for item in _FORBIDDEN_MARKUP:
        if item in lowered:
            raise ThemeRegistrationError(
                f"{where} 违反自包含约束（出现 {item!r}）：SVG 片段不允许脚本 / 外链"
            )
    if _EVENT_HANDLER.search(markup):
        raise ThemeRegistrationError(f"{where} 违反自包含约束：SVG 片段不允许事件处理器")


def svg_data_uri(markup: str) -> str:
    """把内联 SVG 标记编码成自包含 data URI（可直接写进 CSS background-image）。

    编码后 **不会**产生 http 字面量：xmlns 里的协议分隔符同样被百分号编码，
    浏览器解码后仍是标准 SVG 命名空间，因此既能渲染又满足「卡片无外链」约束。
    """
    compact = " ".join(str(markup).split())
    return 'url("data:image/svg+xml,' + quote(compact, safe=" ,()'!*~") + '")'


def _normalize_assets(
    svg_assets: Mapping[str, str] | None, *, theme_id: str
) -> dict[str, str]:
    """把 svg_assets 规范化成 CSS 变量值（--svg-<name>）。"""
    normalized: dict[str, str] = {}
    for name, value in (svg_assets or {}).items():
        key = str(name).strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", key):
            raise ThemeRegistrationError(f"主题 {theme_id!r} 的 SVG 资产名非法: {name!r}")
        raw = str(value).strip()
        if not raw:
            continue
        if raw.startswith("<"):
            _forbid_unsafe_markup(raw, where=f"主题 {theme_id!r} 的 SVG 资产 {key!r}")
            normalized[key] = svg_data_uri(raw)
        else:
            _forbid_unsafe_text(raw, where=f"主题 {theme_id!r} 的 SVG 资产 {key!r}")
            normalized[key] = raw
    return normalized


def _normalize_font_stack(
    fonts: Sequence[str] | str | None, *, theme_id: str
) -> tuple[str, ...]:
    """规范化 CSS 字体族名栈（只允许系统族名，禁止 url()）。"""
    stack: tuple[str, ...]
    if fonts is None:
        return ()
    if isinstance(fonts, str):
        stack = (fonts.strip(),) if fonts.strip() else ()
    else:
        stack = tuple(str(item).strip() for item in fonts if str(item).strip())
    joined = ", ".join(stack)
    if joined:
        _forbid_unsafe_text(joined, where=f"主题 {theme_id!r} 的字体栈")
        if "url(" in joined:
            raise ThemeRegistrationError(
                f"主题 {theme_id!r} 的字体栈不允许 url()：请用系统字体族名或 embed_fonts"
            )
    return stack


def _resolve_font_source(source: Any, base_dir: Path | None) -> Any:
    """把字体来源解析成可读路径；相对路径按 base_dir（再按工作目录）解析。"""
    if isinstance(source, bytes) or not isinstance(source, (str, Path)):
        return source
    candidate = Path(source)
    candidates = [candidate]
    if not candidate.is_absolute() and base_dir is not None:
        candidates.insert(0, Path(base_dir) / candidate)
    for option in candidates:
        try:
            if option.exists():
                return option
        except OSError:  # pragma: no cover - 极端非法路径
            continue
    return candidates[0]


def _normalize_embed_fonts(
    fonts: Sequence[EmbeddedFont | Mapping[str, Any]] | None,
    *,
    theme_id: str,
    base_dir: Path | None = None,
) -> tuple[EmbeddedFont, ...]:
    """规范化内嵌字体列表（相对路径按 base_dir 解析；缺失文件留给渲染期回落）。"""
    normalized: list[EmbeddedFont] = []
    for item in fonts or ():
        if isinstance(item, EmbeddedFont):
            font = item
        elif isinstance(item, Mapping):
            try:
                font = EmbeddedFont(
                    family=str(item["family"]),
                    source=item["source"],
                    format=str(item.get("format") or "truetype"),
                    weight=str(item.get("weight") or "400"),
                    style=str(item.get("style") or "normal"),
                )
            except KeyError as exc:
                raise ThemeRegistrationError(
                    f"主题 {theme_id!r} 的内嵌字体缺少字段 {exc}"
                ) from exc
        else:
            raise ThemeRegistrationError(
                f"主题 {theme_id!r} 的内嵌字体必须是 EmbeddedFont / ThemeFont 或映射"
            )
        if not str(font.family).strip():
            raise ThemeRegistrationError(f"主题 {theme_id!r} 的内嵌字体缺少 family")
        if font.format not in ("woff2", "woff", "truetype", "opentype"):
            raise ThemeRegistrationError(
                f"主题 {theme_id!r} 的内嵌字体 {font.family!r} 格式非法: {font.format!r}"
            )
        resolved = _resolve_font_source(font.source, base_dir)
        if resolved is not font.source:
            font = EmbeddedFont(
                family=font.family,
                source=resolved,
                format=font.format,
                weight=font.weight,
                style=font.style,
            )
        normalized.append(font)
    return tuple(normalized)


def _looks_like_font_files(value: Any) -> bool:
    """判断 fonts= 收到的是「字体文件列表」还是「CSS 字体族名栈」。"""
    if value is None or isinstance(value, str):
        return False
    if not isinstance(value, Sequence):
        return False
    return any(isinstance(item, (EmbeddedFont, Mapping)) for item in value)


def _font_stack_of(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value or "").split(",") if part.strip())

