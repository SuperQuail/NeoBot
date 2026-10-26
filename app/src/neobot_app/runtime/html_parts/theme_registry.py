"""主题注册 API：注册 / 注销 / 查询 / CSS 变量与字体组装。"""

from __future__ import annotations

import base64
import html as html_module
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.screenshot import FontFace

from .base import (
    _CORE_VARIABLE_DEFAULTS,
    _FONT_META_RE,
    _VARIABLE_NAME,
    BUILTIN_THEMES,
    THEMES,
    THEME_SPECS,
    EmbeddedFont,
    ThemeRegistrationError,
    ThemeSpec,
)
from .theme_validation import (
    _forbid_unsafe_markup,
    _forbid_unsafe_text,
    _font_stack_of,
    _looks_like_font_files,
    _normalize_assets,
    _normalize_embed_fonts,
    _normalize_font_stack,
)

logger = get_module_logger("runtime.html_card")


def _builtin_variable_defaults(theme_id: str) -> dict[str, str]:
    """注册期的额外兜底（非核心键）：用内置 default 主题的扩展变量补齐。"""
    # 延迟导入：内置主题包反过来要调用 register_theme，模块级导入会成环。
    from .builtin_themes import _BUILTIN_PACKS

    if theme_id == "default" or "default" not in _BUILTIN_PACKS:
        return {}
    base = _BUILTIN_PACKS["default"]["variables"]
    return {k: v for k, v in base.items() if k not in _CORE_VARIABLE_DEFAULTS}


def register_theme(
    theme_id: str,
    *,
    variables: Mapping[str, str] | None = None,
    fonts: Sequence[str] | str | Sequence[EmbeddedFont | Mapping[str, Any]] | None = (),
    font_stack: Sequence[str] | str | None = None,
    embed_fonts: Sequence[EmbeddedFont | Mapping[str, Any]] | None = (),
    font_base_dir: str | Path | None = None,
    css: str = "",
    background: str = "",
    ornament: str = "",
    emblem: str = "",
    svg_assets: Mapping[str, str] | None = None,
    replace: bool = False,
) -> ThemeSpec:
    """注册（或覆盖）一套卡片主题，返回 ThemeSpec。

    字体有两件**互相独立**的事，都要能声明：

    1. CSS 字体族名栈（写进 --card-font）：用 font_stack=，或 fonts= 传纯字符串列表；
    2. 要内联进临时页的字体文件：用 embed_fonts=，或直接 fonts= 传 EmbeddedFont /
       映射列表；渲染时组装成 RenderOptions.fonts，由 Chromium 逐字形回退。

    插件注册自己的主题（例：Minecraft 主题：内嵌像素字体 + MC 背景）：:

        register_theme(
            "minecraft",
            variables={
                "--card-bg": "#1d1d21",
                "--card-fg": "#f4f4f4",
                "--card-muted": "#a0a0a0",
                "--accent": "#7cc576",
                "--radius": "4px",
                "--card-border": "#3a3a3a",
                "--font-smoothing": "none",
                "--card-font-size": "16px",
            },
            # CSS 栈：拉丁像素字体在前，中日韩像素字体兜底，最后系统等宽
            font_stack=['"Monocraft"', '"FusionPixel"', "ui-monospace", "monospace"],
            embed_fonts=[
                EmbeddedFont("Monocraft", "assets/fonts/Monocraft-Regular.ttf"),
                EmbeddedFont(
                    "FusionPixel",
                    "assets/fonts/FusionPixel8px-zh_hans.woff2",
                    format="woff2",
                ),
            ],
            font_base_dir=Path(__file__).parent,   # 相对路径以此为基准
            background=svg_data_uri("<svg>...</svg>"),   # 或纯 CSS 渐变
            ornament='<svg class="nb-mc">...</svg>',
            svg_assets={"dirt": "<svg>...</svg>"},
        )

    约束（注册时校验，违反直接抛 ThemeRegistrationError）：

    - variables 变量名必须形如 --foo-bar，值不得含外链 / @import / 脚本；
    - 字体栈只接受系统字体族名，禁止 url()（要内嵌字体请用 embed_fonts）；
    - css / ornament / emblem / svg_assets 必须是自包含片段（无外链、无脚本）；
    - 已存在的主题 id 需显式 replace=True 才能覆盖；
    - 字体文件缺失**不算错**：渲染时记 warning 并回落系统字体（绝不让渲染失败）。
    """
    key = str(theme_id or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", key):
        raise ThemeRegistrationError(f"主题 id 非法: {theme_id!r}")
    if key in THEME_SPECS and not replace:
        raise ThemeRegistrationError(f"主题已注册: {key!r}（如需覆盖请传 replace=True）")

    raw_stack: Any = font_stack
    raw_files: Any = embed_fonts
    if _looks_like_font_files(fonts):
        # fonts= 收到字体文件列表：与 embed_fonts= 合并（顺序保持不变）
        raw_files = (*tuple(raw_files or ()), *tuple(fonts or ()))
    elif raw_stack is None:
        raw_stack = fonts

    merged: dict[str, str] = dict(_CORE_VARIABLE_DEFAULTS)
    merged.update(_builtin_variable_defaults(key))
    for name, value in (variables or {}).items():
        var = str(name).strip()
        if not _VARIABLE_NAME.fullmatch(var):
            raise ThemeRegistrationError(f"主题 {key!r} 的变量名非法: {name!r}")
        text = str(value)
        _forbid_unsafe_text(text, where=f"主题 {key!r} 的变量 {var}")
        merged[var] = text

    stack = _normalize_font_stack(raw_stack, theme_id=key)
    if stack:
        merged["--card-font"] = ", ".join(stack)

    base_dir = Path(font_base_dir) if font_base_dir is not None else None
    safe_css = str(css or "")
    if safe_css:
        _forbid_unsafe_text(safe_css, where=f"主题 {key!r} 的 CSS")
    safe_background = str(background or "")
    if safe_background:
        _forbid_unsafe_text(safe_background, where=f"主题 {key!r} 的背景装饰")
        merged["--card-bg-image"] = safe_background
    safe_ornament = str(ornament or "")
    if safe_ornament:
        _forbid_unsafe_markup(safe_ornament, where=f"主题 {key!r} 的插图")
    safe_emblem = str(emblem or "")
    if safe_emblem:
        _forbid_unsafe_markup(safe_emblem, where=f"主题 {key!r} 的徽章")

    assets = _normalize_assets(svg_assets, theme_id=key)
    for asset_name, asset_value in assets.items():
        merged[f"--svg-{asset_name}"] = asset_value

    spec = ThemeSpec(
        id=key,
        variables=merged,
        fonts=stack or _font_stack_of(merged.get("--card-font", "")),
        css=safe_css,
        background=safe_background,
        ornament=safe_ornament,
        emblem=safe_emblem,
        svg_assets=assets,
        embed_fonts=_normalize_embed_fonts(raw_files, theme_id=key, base_dir=base_dir),
    )
    THEME_SPECS[key] = spec
    THEMES[key] = dict(merged)
    return spec


def unregister_theme(theme_id: str) -> bool:
    """注销插件注册的主题；内置主题不可注销（返回 False）。"""
    key = str(theme_id or "").strip().lower()
    if key in BUILTIN_THEMES or key not in THEME_SPECS:
        return False
    THEME_SPECS.pop(key, None)
    THEMES.pop(key, None)
    return True


def registered_themes() -> tuple[str, ...]:
    """当前全部主题 id（内置在前，插件主题按注册顺序）。"""
    builtin = [name for name in BUILTIN_THEMES if name in THEME_SPECS]
    extra = [name for name in THEME_SPECS if name not in BUILTIN_THEMES]
    return tuple(builtin + extra)


def resolve_theme(theme: str | None) -> str:
    """解析主题 id：未知主题回落 default 并记 warning。"""
    name = str(theme or "default").strip().lower() or "default"
    if name not in THEME_SPECS:
        if name != "default":
            logger.warning(f"未知卡片主题，已回落 default: {name!r}")
        return "default"
    return name


def theme_spec(theme: str | None) -> ThemeSpec:
    """主题声明（未知主题回落 default）。"""
    return THEME_SPECS[resolve_theme(theme)]


def get_theme(theme: str | None) -> ThemeSpec:
    """theme_spec 的别名（对外更直观）。"""
    return theme_spec(theme)


def theme_variables(theme: str | None) -> str:
    """主题的 CSS 变量块（可直接内联进 :root）。"""
    variables = THEMES[resolve_theme(theme)]
    body = "\n".join(f"  {key}: {value};" for key, value in variables.items())
    return f":root {{\n{body}\n}}"


def theme_css(theme: str | None) -> str:
    """主题专属 CSS 片段（已通过自包含校验）。"""
    return theme_spec(theme).css


def theme_svg(theme: str | None, name: str) -> str:
    """主题的某个 SVG 资产值（形如 url("data:image/svg+xml,...")）；不存在返回空串。"""
    return theme_spec(theme).svg_assets.get(str(name).strip().lower(), "")


def card_fonts(html: str) -> tuple[FontFace, ...]:
    """从卡片 HTML 的内嵌字体清单里读回 FontFace（没有清单时返回空元组）。"""
    match = _FONT_META_RE.search(str(html or ""))
    if match is None:
        return ()
    try:
        entries = json.loads(html_module.unescape(match.group(1)))
    except (ValueError, TypeError):
        logger.warning("卡片内嵌字体清单解析失败，已忽略")
        return ()
    faces: list[FontFace] = []
    for entry in entries if isinstance(entries, list) else ():
        if not isinstance(entry, Mapping):
            continue
        family = str(entry.get("family") or "").strip()
        if not family:
            continue
        source: Path | bytes | None = None
        data = entry.get("data")
        if isinstance(data, str) and data:
            try:
                source = base64.b64decode(data)
            except (ValueError, TypeError):
                source = None
        elif entry.get("path"):
            source = Path(str(entry["path"]))
        if source is None:
            continue
        try:
            faces.append(
                FontFace(
                    family=family,
                    source=source,
                    format=str(entry.get("format") or "truetype"),  # type: ignore[arg-type]
                    weight=str(entry.get("weight") or "400"),
                    style=str(entry.get("style") or "normal"),
                )
            )
        except (TypeError, ValueError):
            logger.warning(f"内嵌字体条目非法，已忽略: {family!r}")
    return tuple(faces)


