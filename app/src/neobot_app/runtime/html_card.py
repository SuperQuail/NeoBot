"""公共 HTML 卡片渲染器（多主题 / 主题注册 / 专属字体 / 自包含美术）。

/help、/status 与游戏卡片共用同一份实现：

- render_card_html 生成**自包含** HTML：内联 CSS、无 JS、无外链、无外部资源
  （禁止 http(s) 链接、@import、外链字体与图片）；
- 每个主题 = 一份 CSS 变量 + 一段主题 CSS + 内联 SVG 装饰（背景纹理 / 徽章 / 插图），
  外加可选的**专属字体栈**与**内嵌字体文件**；
- render_card_image 走既有的 ScreenshotService（与 markdown→图片共享同一个
  operation_lock）；不可用或失败一律返回 None，**不抛异常**，由调用方降级。

主题注册（插件可用）：register_theme(theme_id, ...) / unregister_theme / get_theme。
未知主题回落 default 并记 warning（既有语义不变）。

安全边界（硬红线，不可回归）：

1. 用户可控文本一律 _escape（html.escape, quote=True）后进文本节点，
   绝不进标签名、属性名或属性值；
2. 主题注册的 CSS / SVG 片段是**可信片段**，注册时会被自包含校验
   （禁外链、禁脚本、禁 @import），校验不过直接拒绝注册；
3. 插槽（slot）与标记（marker）只接受严格字符集的名字，注入的片段由调用方
   保证「不含任何用户输入」——用户文本必须先 escape → Markdown → URL 清洗。
"""

from __future__ import annotations

import base64
import html as html_module
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.screenshot import (
    FontFace,
    RenderOptions,
    ScreenshotOptions,
    ScreenshotPort,
)

logger = get_module_logger("runtime.html_card")

#: 默认卡片宽度（px）
DEFAULT_WIDTH = 720

#: 卡片外层元素选择器（render_card_html 固定输出 <main class="card">）。
#: 截图用它裁剪到卡片本身，避免 full_page 按浏览器视口留出大片空白。
_CARD_SELECTOR = "main.card"

#: 卡片容器选择器（对外暴露，供测试与文档引用）
CARD_SELECTOR = _CARD_SELECTOR

#: 内嵌字体清单的 meta 标签名（render_card_image 从 HTML 里读回字体）
FONT_META_NAME = "neobot-card-fonts"

#: 内嵌字体清单的 meta 标签正则（content 已被 html.escape，故不含裸引号）
_FONT_META_RE = re.compile(
    r'<meta\s+name="' + FONT_META_NAME + r'"\s+content="([^"]*)"\s*/?>'
)

#: 变量名 / 插槽名 / 标记名 / 表格列宽 的严格字符集
_VARIABLE_NAME = re.compile(r"^--[a-z0-9][a-z0-9-]{0,47}$")
_SLOT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_MARKER_NAME = re.compile(r"^@@[A-Z0-9][A-Z0-9_]{0,39}@@$")
_WIDTH_VALUE = re.compile(r"^\d{1,3}(?:\.\d{1,2})?(?:%|px)$")
_VARIANT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")

#: 主题声明的合法色调（tone）
_TONES = ("accent", "ok", "warn", "danger", "muted")

#: 自包含约束：主题 CSS / 片段里一律不许出现这些串
_FORBIDDEN_TEXT = (
    "http://",
    "https://",
    "@import",
    "<script",
    "</style",
    "javascript:",
    "<iframe",
    "<object",
    "<embed",
)
_FORBIDDEN_MARKUP = (
    "<script",
    "<foreignobject",
    "javascript:",
    "xlink:href",
    "<image",
    "<iframe",
    "<object",
    "<embed",
)
_EVENT_HANDLER = re.compile(r"""[\s"']on[a-z]{3,}\s*=""", re.IGNORECASE)


class ThemeRegistrationError(ValueError):
    """主题注册参数非法（变量名 / 字体栈 / CSS / SVG 片段 / 重复注册）。"""


# ----------------------------------------------------------------------
# 主题声明
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddedFont:
    """主题内嵌字体：运行时会以 data URI 注入临时页（不走外链）。

    source 可以是字体文件路径（str / Path）或字体字节（bytes）。
    format 取 screenshot 契约支持的 woff2 / woff / truetype / opentype。
    """

    family: str
    source: Path | bytes | str
    format: str = "truetype"
    weight: str = "400"
    style: str = "normal"

    def font_face(self) -> FontFace:
        """转换为截图端口契约的 FontFace。"""
        source: Path | bytes = (
            self.source if isinstance(self.source, bytes) else Path(self.source)
        )
        return FontFace(
            family=str(self.family),
            source=source,
            format=self.format,  # type: ignore[arg-type]
            weight=str(self.weight),
            style=str(self.style),
        )


@dataclass(frozen=True)
class ThemeSpec:
    """一套主题的完整声明。

    - variables: CSS 变量（至少含 --card-bg / --card-fg / --card-muted /
      --accent / --radius / --card-border / --card-font 七个核心键，
      注册时缺失的键会用 default 主题补齐）；
    - fonts: 专属字体栈（写入 --card-font）；
    - css: 主题专属 CSS（可信片段，注册时校验自包含）；
    - background: 背景装饰层（纯 CSS 渐变或 svg_data_uri() 产物）；
    - ornament: 卡片底纹 / 插图的**内联 SVG**（可信片段）；
    - emblem: 标题右侧徽章的**内联 SVG**（可信片段）；
    - svg_assets: 命名的 SVG 资产，注册后以 CSS 变量 --svg-<name> 暴露；
    - embed_fonts: 内嵌字体文件，渲染时组装进 RenderOptions.fonts。
    """

    id: str
    variables: Mapping[str, str] = field(default_factory=dict)
    fonts: tuple[str, ...] = ()
    css: str = ""
    background: str = ""
    ornament: str = ""
    emblem: str = ""
    svg_assets: Mapping[str, str] = field(default_factory=dict)
    embed_fonts: tuple[EmbeddedFont, ...] = ()


#: 主题 id -> CSS 变量块（既有对外结构保持不变：dict[str, dict[str, str]]）
THEMES: dict[str, dict[str, str]] = {}

#: 主题 id -> 完整声明（含内嵌字体 / SVG 资产等）
THEME_SPECS: dict[str, ThemeSpec] = {}

#: 四套内置主题（顺序即对外展示顺序）
BUILTIN_THEMES: tuple[str, ...] = ("default", "bottle", "game", "fortune")

#: 主题 id 的对外顺序（内置主题；插件主题见 registered_themes()）
THEME_NAMES: tuple[str, ...] = BUILTIN_THEMES

#: default 主题的核心兜底变量（注册主题缺键时补齐，保证任何主题都能出图）
_CORE_VARIABLE_DEFAULTS: dict[str, str] = {
    "--card-bg": "#12151c",
    "--card-fg": "#e6edf3",
    "--card-muted": "#8b949e",
    "--accent": "#4493f8",
    "--radius": "14px",
    "--card-border": "#232a35",
    "--card-font": (
        'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", '
        '"PingFang SC", "Hiragino Sans GB", sans-serif'
    ),
}


#: EmbeddedFont 的别名（插件侧更直观的写法）
ThemeFont = EmbeddedFont


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


def _builtin_variable_defaults(theme_id: str) -> dict[str, str]:
    """注册期的额外兜底（非核心键）：用内置 default 主题的扩展变量补齐。"""
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
# 四套内置主题（variables / css / ornament / emblem / svg_assets）
# ----------------------------------------------------------------------

#: 内置主题包的声明式描述（由 _install_builtin_themes 统一走 register_theme 注册，
#: 因此内置主题与插件主题受同一套自包含校验，行为完全一致）。
_BUILTIN_PACKS: dict[str, dict[str, Any]] = {
    # ── 极简深夜：冷色玻璃面板 + 细网格 + 顶部辉光 ──────────────
    "default": {
        "variables": {
            "--card-bg": "#0f131b",
            "--card-fg": "#e6edf3",
            "--card-muted": "#8b98a9",
            "--accent": "#4493f8",
            "--radius": "16px",
            "--card-border": "#222c3a",
            "--font-smoothing": "antialiased",
            "--card-font-size": "15px",
            "--card-pad": "22px 24px 18px",
            "--card-shadow": "0 14px 36px rgba(0, 0, 0, 0.45)",
            "--panel-bg": "rgba(255, 255, 255, 0.032)",
            "--panel-border": "#222c3a",
            "--panel-radius": "12px",
            "--panel-pad": "13px 15px",
            "--panel-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.03)",
            "--tile-bg": "rgba(255, 255, 255, 0.05)",
            "--tile-radius": "10px",
            "--hairline": "rgba(139, 152, 169, 0.22)",
            "--zebra": "rgba(255, 255, 255, 0.022)",
            "--table-head-bg": "rgba(255, 255, 255, 0.04)",
            "--title-size": "23px",
            "--title-weight": "800",
            "--title-tracking": "0.01em",
            "--head-rule": "linear-gradient(90deg, #4493f8, rgba(68, 147, 248, 0))",
            "--head-rule-width": "86px",
            "--heading-size": "15px",
            "--heading-color": "#7fb6ff",
            "--heading-tracking": "0.06em",
            "--accent-soft": "rgba(68, 147, 248, 0.16)",
            "--card-bg-image": (
                "radial-gradient(120% 90% at 8% -18%, rgba(68, 147, 248, 0.20),"
                " rgba(68, 147, 248, 0) 60%),"
                " radial-gradient(70% 50% at 100% 0%, rgba(126, 231, 135, 0.07),"
                " rgba(0, 0, 0, 0) 62%)"
            ),
        },
        "css": """\
/* 两层都是柔和渐变：各自铺一次，不要平铺 */
.card-veil { background-repeat: no-repeat, no-repeat; }
.card-emblem { filter: drop-shadow(0 0 10px rgba(68, 147, 248, 0.35)); }
.stat--ok .stat-value { text-shadow: 0 0 12px rgba(63, 185, 80, 0.30); }
.block--stats .block-subheading { letter-spacing: 0.16em; }
.rows--commands tbody tr:nth-child(odd) { box-shadow: inset 2px 0 0 rgba(68, 147, 248, 0.20); }
""",
        "ornament": (
            '<svg class="nb-decor nb-grid" width="100%" height="100%" aria-hidden="true">'
            '<defs><pattern id="nbGridLine" width="28" height="28" patternUnits="userSpaceOnUse">'
            '<path d="M28 0H0V28" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            "</pattern></defs>"
            '<rect width="100%" height="100%" fill="url(#nbGridLine)"/>'
            "</svg>"
        ),
        "emblem": (
            '<svg viewBox="0 0 40 40" width="100%" height="100%" fill="none">'
            '<path d="M20 3.2 34.8 11v18L20 36.8 5.2 29V11z" stroke="currentColor"'
            ' stroke-width="2" stroke-linejoin="round" opacity="0.9"/>'
            '<path d="M11.5 21.5h4.6l2.6-6.2 3.1 11 2.4-4.8h4.3" stroke="currentColor"'
            ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg>"
        ),
    },
    # ── 深海漂流瓶：海蓝渐变 + 波浪 + 气泡 + 衬线正文 ──────────
    "bottle": {
        "font_stack": (
            'Georgia, "Songti SC", "SimSun", "Noto Serif SC", "Source Han Serif SC", serif'
        ),
        "variables": {
            "--card-bg": "linear-gradient(165deg, #072033 0%, #0d3d61 46%, #17678f 100%)",
            "--card-fg": "#eef7ff",
            "--card-muted": "#9dc3e0",
            "--accent": "#63c8ff",
            "--radius": "22px",
            "--card-border": "rgba(157, 195, 224, 0.42)",
            "--card-pad": "24px 26px 20px",
            "--card-shadow": "0 16px 40px rgba(2, 16, 30, 0.55)",
            "--panel-bg": "rgba(255, 255, 255, 0.07)",
            "--panel-border": "rgba(157, 195, 224, 0.34)",
            "--panel-radius": "14px",
            "--panel-pad": "13px 16px",
            "--panel-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.16)",
            "--tile-bg": "rgba(255, 255, 255, 0.09)",
            "--tile-radius": "12px",
            "--hairline": "rgba(157, 195, 224, 0.30)",
            "--zebra": "rgba(157, 195, 224, 0.09)",
            "--table-head-bg": "rgba(255, 255, 255, 0.10)",
            "--title-size": "24px",
            "--title-weight": "700",
            "--title-tracking": "0.02em",
            "--title-shadow": "0 2px 12px rgba(2, 16, 30, 0.45)",
            "--head-rule": "linear-gradient(90deg, #9fe6ff, rgba(99, 200, 255, 0))",
            "--head-rule-width": "96px",
            "--heading-size": "15.5px",
            "--heading-color": "#a8dcff",
            "--heading-tracking": "0.05em",
            "--accent-soft": "rgba(99, 200, 255, 0.20)",
            "--card-bg-image": (
                "radial-gradient(90% 60% at 50% -12%, rgba(180, 235, 255, 0.30),"
                " rgba(180, 235, 255, 0) 62%)"
            ),
        },
        "css": """\
.card { box-shadow: var(--card-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.22); }
.card-veil { background-repeat: no-repeat; }
.block--kv, .block--rows { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14), 0 8px 20px rgba(2, 16, 30, 0.22); }
.card-footer { font-style: italic; letter-spacing: 0.02em; }
.note { font-style: italic; }
.rows thead th { letter-spacing: 0.14em; }
.nb-bubbles { opacity: 0.9; }
""",
        "ornament": (
            '<svg class="nb-decor nb-bubbles" width="100%" height="100%" aria-hidden="true">'
            '<g fill="rgba(190, 235, 255, 0.13)">'
            '<circle cx="88%" cy="14%" r="9"/><circle cx="93%" cy="23%" r="4"/>'
            '<circle cx="80%" cy="36%" r="6"/><circle cx="90%" cy="52%" r="10"/>'
            '<circle cx="84%" cy="66%" r="5"/><circle cx="9%" cy="30%" r="4"/>'
            '<circle cx="6%" cy="47%" r="7"/><circle cx="13%" cy="63%" r="3"/>'
            '<circle cx="20%" cy="80%" r="5"/>'
            "</g></svg>"
            '<svg class="nb-decor nb-waves" viewBox="0 0 720 130" preserveAspectRatio="none"'
            ' aria-hidden="true">'
            '<path d="M0 58c70-28 130 22 200 6s130-34 200-12 130 34 200 14 120-24 120-24v88H0z"'
            ' fill="rgba(99, 200, 255, 0.12)"/>'
            '<path d="M0 84c80-24 140 18 210 4s140-28 210-8 140 28 210 10 90-14 90-14v62H0z"'
            ' fill="rgba(99, 200, 255, 0.20)"/>'
            "</svg>"
        ),
        "emblem": (
            '<svg viewBox="0 0 40 40" width="100%" height="100%" fill="none"'
            ' stroke="currentColor" stroke-width="2" stroke-linejoin="round">'
            '<path d="M16 3.5h8v5c0 1.7.7 2.8 2 4.1 1.1 1.2 1.6 2.6 1.6 4.4v13.5a3 3 0 0 1-3 3h-9.2a3 3 0 0 1-3-3V17c0-1.8.5-3.2 1.6-4.4 1.3-1.3 2-2.4 2-4.1z"/>'
            '<path d="M12.6 24.5c2.4 0 2.4 1.8 4.8 1.8s2.4-1.8 4.8-1.8 2.4 1.8 4.8 1.8" stroke-width="1.7"/>'
            '<path d="M12.6 29.3c2.4 0 2.4 1.8 4.8 1.8s2.4-1.8 4.8-1.8 2.4 1.8 4.8 1.8" stroke-width="1.7" opacity="0.6"/>'
            "</svg>"
        ),
    },
    # ── 街机像素：紫底 + 像素网格 + 硬边阴影 + 等宽字体 ─────────
    "game": {
        "font_stack": (
            'ui-monospace, "Cascadia Mono", "Consolas", "Microsoft YaHei", monospace'
        ),
        "variables": {
            "--card-bg": "#1b1035",
            "--card-fg": "#fdf6ff",
            "--card-muted": "#bda9e8",
            "--accent": "#ffd447",
            "--radius": "6px",
            "--card-border": "#7a4dff",
            "--card-border-width": "2px",
            "--font-smoothing": "antialiased",
            "--card-font-size": "15px",
            "--card-pad": "20px 22px 18px",
            "--card-shadow": "0 0 0 2px rgba(122, 77, 255, 0.22), 9px 9px 0 rgba(122, 77, 255, 0.26)",
            "--panel-bg": "rgba(122, 77, 255, 0.16)",
            "--panel-border": "rgba(160, 120, 255, 0.46)",
            "--panel-radius": "4px",
            "--panel-pad": "12px 14px",
            "--panel-shadow": "none",
            "--tile-bg": "rgba(255, 212, 71, 0.09)",
            "--tile-radius": "3px",
            "--hairline": "rgba(160, 120, 255, 0.34)",
            "--zebra": "rgba(255, 212, 71, 0.055)",
            "--table-head-bg": "rgba(122, 77, 255, 0.24)",
            "--title-size": "23px",
            "--title-weight": "800",
            "--title-tracking": "0.06em",
            "--title-shadow": "3px 3px 0 rgba(122, 77, 255, 0.70)",
            "--head-rule": (
                "repeating-linear-gradient(90deg, #ffd447 0 10px, rgba(255, 212, 71, 0) 10px 20px)"
            ),
            "--head-rule-width": "120px",
            "--heading-size": "15px",
            "--heading-color": "#ffd447",
            "--heading-tracking": "0.08em",
            "--accent-soft": "rgba(255, 212, 71, 0.20)",
            "--card-bg-image": (
                "linear-gradient(rgba(255, 212, 71, 0.05) 1px, transparent 1px),"
                " linear-gradient(90deg, rgba(255, 212, 71, 0.05) 1px, transparent 1px)"
            ),
        },
        "css": """\
.card-veil { background-size: 8px 8px, 8px 8px; }
.block--kv::after, .block--rows::after, .block--stats::after {
  content: ""; position: absolute; top: -2px; right: -2px; width: 12px; height: 12px;
  background: var(--accent); clip-path: polygon(100% 0, 0 0, 100% 100%); opacity: 0.8;
}
.block-heading::before { box-shadow: 0 0 0 2px rgba(255, 212, 71, 0.22); }
.rows thead th { border-bottom: 2px solid var(--accent); }
.card-emblem { filter: drop-shadow(2px 2px 0 rgba(122, 77, 255, 0.85)); }
.stat-value { letter-spacing: 0.02em; }
.card-footer::before { background: var(--accent); }
""",
        "ornament": (
            '<svg class="nb-decor" width="100%" height="100%" aria-hidden="true">'
            '<g fill="rgba(255, 212, 71, 0.45)">'
            '<rect x="0" y="0" width="6" height="6"/><rect x="12" y="0" width="6" height="6"/>'
            '<rect x="0" y="12" width="6" height="6"/>'
            '<rect x="0" y="0" width="6" height="6" transform="translate(0 0)"/>'
            "</g>"
            '<g fill="rgba(122, 77, 255, 0.35)">'
            '<rect x="100%" y="100%" width="0" height="0"/>'
            "</g>"
            "</svg>"
        ),
        "emblem": (
            '<svg viewBox="0 0 40 40" width="100%" height="100%">'
            '<g fill="currentColor">'
            '<rect x="15.5" y="4.5" width="9" height="31" rx="2"/>'
            '<rect x="4.5" y="15.5" width="31" height="9" rx="2"/>'
            '<rect x="30.5" y="3.5" width="5" height="5"/>'
            '<rect x="3.5" y="30.5" width="5" height="5"/>'
            "</g>"
            '<rect x="17.5" y="17.5" width="5" height="5" fill="#1b1035"/>'
            "</svg>"
        ),
    },
    # ── 中式签纸：宣纸底 + 回纹 + 朱红 + 宋体/楷体 + 竹签插图 ────
    "fortune": {
        "font_stack": '"Songti SC", "SimSun", "STSong", "Noto Serif SC", serif',
        "variables": {
            "--card-bg": "linear-gradient(168deg, #fffdf7 0%, #fdf1dc 46%, #f7e2bd 100%)",
            "--card-fg": "#4a2b12",
            "--card-muted": "#8a6135",
            "--accent": "#c8382b",
            "--radius": "14px",
            "--card-border": "#e0bd8b",
            "--card-pad": "22px 24px 20px",
            "--card-shadow": "0 14px 30px rgba(120, 72, 20, 0.20)",
            "--panel-bg": "rgba(255, 255, 255, 0.64)",
            "--panel-border": "#ecd9b4",
            "--panel-radius": "10px",
            "--panel-pad": "12px 15px",
            "--panel-shadow": "inset 0 0 0 1px rgba(255, 255, 255, 0.75)",
            "--tile-bg": "rgba(200, 56, 43, 0.05)",
            "--tile-radius": "8px",
            "--hairline": "#e9d5b0",
            "--zebra": "rgba(200, 56, 43, 0.045)",
            "--table-head-bg": "rgba(200, 56, 43, 0.07)",
            "--title-font": '"Kaiti SC", "KaiTi", "STKaiti", "Songti SC", serif',
            "--title-size": "26px",
            "--title-weight": "700",
            "--title-tracking": "0.08em",
            "--title-color": "#7d2417",
            "--title-shadow": "0 1px 0 rgba(255, 255, 255, 0.9)",
            "--head-rule": "linear-gradient(90deg, #c8382b, rgba(200, 56, 43, 0))",
            "--head-rule-width": "104px",
            "--heading-size": "16px",
            "--heading-color": "#a83224",
            "--heading-tracking": "0.10em",
            "--accent-soft": "rgba(200, 56, 43, 0.12)",
            "--card-bg-image": (
                "radial-gradient(110% 70% at 50% -10%, rgba(255, 255, 255, 0.85),"
                " rgba(255, 255, 255, 0) 60%)"
            ),
        },
        "css": """\
.card-veil { background-repeat: no-repeat; }
.card-head { position: relative; }
.card-head::after { height: 3px; }
.block-heading::before { width: 5px; border-radius: 1px; }
.rows thead th { letter-spacing: 0.18em; }
.card-footer::before { background: var(--head-rule); }
.nb-bamboo { left: auto; right: 12px; top: 8px; bottom: auto; width: 92px; height: 330px; opacity: 0.45; }
.nb-meander { opacity: 0.75; }
.nb-seal { left: auto; right: 20px; top: auto; bottom: 14px; width: 64px; height: 64px; opacity: 0.5; }
.card-emblem { color: var(--accent); }
""",
        "ornament": (
            '<svg class="nb-decor nb-meander" width="100%" height="100%" aria-hidden="true">'
            '<defs><pattern id="nbMeander" width="26" height="26" patternUnits="userSpaceOnUse">'
            '<path d="M5 21V5h16v12H9V9h8" fill="none" stroke="rgba(200, 56, 43, 0.10)"'
            ' stroke-width="1.4"/></pattern></defs>'
            '<rect width="100%" height="100%" fill="url(#nbMeander)"/>'
            "</svg>"
            '<svg class="nb-decor nb-bamboo" viewBox="0 0 110 380" aria-hidden="true">'
            "<defs>"
            '<linearGradient id="nbStick" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="#efdcb2"/><stop offset="0.42" stop-color="#fdf3da"/>'
            '<stop offset="1" stop-color="#d6b882"/></linearGradient>'
            "</defs>"
            '<path d="M38 44h30v292l-15 30-15-30z" fill="url(#nbStick)" stroke="#c8a86a"'
            ' stroke-width="1.4"/>'
            '<path d="M38 132h30M38 226h30M38 314h30" stroke="#c9a86c" stroke-width="1.8"'
            ' opacity="0.65"/>'
            '<rect x="35" y="20" width="36" height="40" rx="9" fill="#c8382b"/>'
            '<rect x="35" y="20" width="36" height="40" rx="9" fill="none" stroke="#9c2a20"'
            ' stroke-width="1.4"/>'
            '<g fill="#b3352a" font-family="Kaiti SC, KaiTi, STKaiti, serif" font-size="24"'
            ' text-anchor="middle">'
            '<text x="53" y="82">\u4e0a</text>'
            '<text x="53" y="108">\u4e0a</text>'
            '<text x="53" y="134">\u7b7e</text>'
            "</g>"
            "</svg>"
            '<svg class="nb-decor nb-seal" viewBox="0 0 72 72" aria-hidden="true">'
            '<rect x="4" y="4" width="64" height="64" rx="11" fill="none" stroke="#c8382b"'
            ' stroke-width="4"/>'
            '<g fill="#c8382b" font-family="Kaiti SC, KaiTi, STKaiti, serif" font-size="24"'
            ' text-anchor="middle">'
            '<text x="36" y="34">\u5927</text>'
            '<text x="36" y="60">\u5409</text>'
            "</g></svg>"
        ),
        "emblem": (
            '<svg viewBox="0 0 40 40" width="100%" height="100%">'
            '<rect x="5" y="5" width="30" height="30" rx="7" fill="none" stroke="currentColor"'
            ' stroke-width="2.6"/>'
            '<g fill="currentColor" font-family="Kaiti SC, KaiTi, STKaiti, serif" font-size="19"'
            ' text-anchor="middle">'
            '<text x="20" y="27.5">\u7b7e</text>'
            "</g></svg>"
        ),
    },
}


def _install_builtin_themes() -> None:
    """注册四套内置主题（与插件主题走同一条注册路径与校验）。"""
    for theme_id in BUILTIN_THEMES:
        register_theme(theme_id, replace=True, **_BUILTIN_PACKS[theme_id])


_install_builtin_themes()


# ----------------------------------------------------------------------
# 公共样式（主题变量 + 组件；全部用 var(--x, fallback) 保持可缺失）
# ----------------------------------------------------------------------

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title_text}</title>
{font_meta}<style>
{variables}
{common}
{theme_css}
</style>
</head>
<body>
<main class="card" style="width: {width}px;">
{decor}
<div class="card-veil" aria-hidden="true"></div>
<header class="card-head">
<div class="card-head-main">
<h1 class="card-title">{title}</h1>
{subtitle}
</div>
{emblem}
</header>
<section class="card-body">
{body}
</section>
{footer}
</main>
</body>
</html>
"""

_COMMON_CSS = """\
/* ── 缺省视觉变量（主题 :root 优先级更高，缺键时用这里的兜底） ── */
:where(:root) {
  --card-pad: 22px 24px 18px;
  --card-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  --card-border-width: 1px;
  --card-font-size: 15px;
  --font-smoothing: antialiased;
  --line: 1.6;
  --block-gap: 14px;
  --panel-bg: rgba(255, 255, 255, 0.035);
  --panel-border: var(--card-border);
  --panel-radius: 12px;
  --panel-pad: 13px 15px;
  --panel-shadow: none;
  --tile-bg: rgba(255, 255, 255, 0.05);
  --tile-radius: 10px;
  --grid-gap: 12px;
  --hairline: var(--card-border);
  --zebra: rgba(255, 255, 255, 0.025);
  --table-head-bg: rgba(255, 255, 255, 0.04);
  --table-font-size: 13.5px;
  --cell-pad: 6px 10px;
  --kv-label-width: 38%;
  --title-font: var(--card-font);
  --title-size: 22px;
  --title-weight: 700;
  --title-tracking: 0.01em;
  --title-color: var(--card-fg);
  --title-shadow: none;
  --head-rule: linear-gradient(90deg, var(--accent), rgba(0, 0, 0, 0));
  --head-rule-width: 80px;
  --heading-size: 15px;
  --heading-color: var(--accent);
  --heading-tracking: 0.05em;
  --subheading-color: var(--card-muted);
  --accent-soft: rgba(127, 127, 127, 0.16);
  --danger: #f85149;
  --danger-soft: rgba(248, 81, 73, 0.13);
  --danger-border: rgba(248, 81, 73, 0.55);
  --ok: #3fb950;
  --ok-soft: rgba(63, 185, 80, 0.13);
  --warn: #d29922;
  --warn-soft: rgba(210, 153, 34, 0.14);
  --muted-soft: rgba(139, 148, 158, 0.14);
  --stat-label-size: 11px;
  --stat-value-size: 16px;
  --emblem-size: 34px;
  --emblem-opacity: 0.95;
  --muted-size: 12px;
  --card-bg-position: 0 0;
  --card-bg-size: auto;
  --card-bg-repeat: repeat;
  --card-bg-opacity: 1;
  --pager-bg: rgba(255, 255, 255, 0.05);
  --pager-border: var(--card-border);
  --note-bg: rgba(127, 127, 127, 0.12);
  --note-bar: var(--accent);
  --cell-line-gap: 2px;
}

/* ── 卡片外壳 ── */
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--card-bg);
  color: var(--card-fg);
  font-family: var(--card-font);
  font-size: var(--card-font-size);
  line-height: var(--line);
  -webkit-font-smoothing: var(--font-smoothing);
}
.card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  padding: var(--card-pad);
  border: var(--card-border-width) solid var(--card-border);
  border-radius: var(--radius);
  background: var(--card-bg);
  box-shadow: var(--card-shadow);
  color: var(--card-fg);
  font-family: var(--card-font);
  font-size: var(--card-font-size);
}
.card-veil {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: var(--card-bg-image, none);
  background-size: var(--card-bg-size);
  background-repeat: var(--card-bg-repeat);
  background-position: var(--card-bg-position);
  opacity: var(--card-bg-opacity);
}
.nb-decor {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.card > .card-head, .card > .card-body, .card > .card-footer {
  position: relative;
  z-index: 1;
}

/* ── 标题区 ── */
.card-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 13px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 15px;
}
.card-head::after {
  content: "";
  position: absolute;
  left: 0;
  bottom: -1px;
  width: var(--head-rule-width);
  height: 2px;
  border-radius: 2px;
  background: var(--head-rule);
}
.card-head-main { flex: 1 1 auto; min-width: 0; }
.card-title {
  margin: 0;
  font-family: var(--title-font);
  font-size: var(--title-size);
  font-weight: var(--title-weight);
  letter-spacing: var(--title-tracking);
  line-height: 1.25;
  color: var(--title-color);
  text-shadow: var(--title-shadow);
}
.card-subtitle {
  margin-top: 6px;
  font-size: 12.5px;
  letter-spacing: 0.02em;
  color: var(--card-muted);
}
.card-emblem {
  flex: 0 0 auto;
  width: var(--emblem-size);
  height: var(--emblem-size);
  opacity: var(--emblem-opacity);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-emblem svg { display: block; width: 100%; height: 100%; }

/* ── 内容区与分区 ── */
.card-body { display: block; }
.block { position: relative; margin: 0 0 var(--block-gap); }
.block:last-child { margin-bottom: 0; }
.block--kv, .block--rows {
  padding: var(--panel-pad);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  background: var(--panel-bg);
  box-shadow: var(--panel-shadow);
}
.block--heading, .block--stats, .block--note, .block--grid { padding: 0; border: 0; background: none; box-shadow: none; }
.block--heading { margin-bottom: 9px; }
.block--heading:not(:first-child) { margin-top: 6px; }
.block--slot, .block--marker { padding: 0; border: 0; background: none; box-shadow: none; }
.card-slot:empty { display: none; }

.block-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: var(--heading-size);
  font-weight: 700;
  letter-spacing: var(--heading-tracking);
  color: var(--heading-color);
}
.block-heading::before {
  content: "";
  flex: 0 0 auto;
  width: 4px;
  height: 0.98em;
  border-radius: 2px;
  background: var(--heading-color);
}
.block-subheading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--subheading-color);
}
.block-subheading::before {
  content: "";
  flex: 0 0 auto;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.85;
}

/* ── 告警 / 状态色调 ── */
.tone-danger { --panel-border: var(--danger-border); --panel-bg: var(--danger-soft); --heading-color: var(--danger); --subheading-color: var(--danger); --note-bar: var(--danger); --note-bg: var(--danger-soft); }
.tone-warn { --panel-border: var(--warn); --panel-bg: var(--warn-soft); --heading-color: var(--warn); --subheading-color: var(--warn); --note-bar: var(--warn); --note-bg: var(--warn-soft); }
.tone-ok { --heading-color: var(--ok); --subheading-color: var(--ok); --note-bar: var(--ok); }
.tone-muted { --heading-color: var(--card-muted); --subheading-color: var(--card-muted); --note-bar: var(--card-muted); }
.tone-danger.block--kv::before, .tone-danger.block--rows::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--danger);
}
.tone-warn.block--kv::before, .tone-warn.block--rows::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--warn);
}

/* ── 键值表 ── */
table.kv, table.rows {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  font-size: var(--table-font-size);
}
.kv th, .kv td { padding: var(--cell-pad); text-align: left; vertical-align: top; border-bottom: 1px solid var(--hairline); }
.kv tr:last-child th, .kv tr:last-child td { border-bottom: 0; }
.kv th { width: var(--kv-label-width); font-weight: 500; color: var(--card-muted); letter-spacing: 0.01em; }
.grid .kv th { width: var(--grid-kv-label-width, 46%); }
.kv td { font-variant-numeric: tabular-nums; font-weight: 550; }

/* ── 数据表（表头 + 斑马纹） ── */
.rows thead th {
  padding: var(--cell-pad);
  text-align: left;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.10em;
  color: var(--card-muted);
  background: var(--table-head-bg);
  border-bottom: 1px solid var(--hairline);
}
.rows thead th:first-child { border-top-left-radius: 6px; }
.rows thead th:last-child { border-top-right-radius: 6px; }
.rows tbody td { padding: var(--cell-pad); text-align: left; vertical-align: top; border-bottom: 1px solid var(--hairline); }
.rows tbody tr:last-child td { border-bottom: 0; }
.rows tbody tr:nth-child(odd) { background: var(--zebra); }
.rows--commands { table-layout: fixed; font-size: 13px; }
.rows--commands thead th, .rows--commands tbody td { padding: 4px 10px; line-height: 1.45; }
.rows--commands tbody td:first-child { color: var(--card-fg); font-weight: 600; overflow-wrap: anywhere; }
.rows--commands tbody td:nth-child(2) { overflow-wrap: anywhere; }
.rows--commands tbody td:last-child { white-space: nowrap; font-size: 11.5px; color: var(--card-muted); }
.cell-line { display: block; }
.cell-line + .cell-line { margin-top: var(--cell-line-gap); color: var(--card-muted); }
.cell--mono { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 0.97em; }
.cell--chip {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.92em;
}
.cell--ok { color: var(--ok); font-weight: 650; }
.cell--warn { color: var(--warn); font-weight: 650; }
.cell--danger { color: var(--danger); font-weight: 650; }
.cell--muted { color: var(--card-muted); }
.cell--accent { color: var(--accent); font-weight: 650; }

/* ── 指标卡片（stats） ── */
.stats { display: grid; grid-template-columns: repeat(var(--stat-cols, 3), minmax(0, 1fr)); gap: 9px; }
.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  padding: 9px 11px;
  border: 1px solid var(--panel-border);
  border-radius: var(--tile-radius);
  background: var(--tile-bg);
}
.stat-label { font-size: var(--stat-label-size); letter-spacing: 0.08em; color: var(--card-muted); }
.stat-value {
  font-size: var(--stat-value-size);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.stat--ok .stat-value { color: var(--ok); }
.stat--warn .stat-value { color: var(--warn); }
.stat--danger .stat-value { color: var(--danger); }
.stat--accent .stat-value { color: var(--accent); }
.stat--muted .stat-value { color: var(--card-muted); }

/* ── 栅格分组（grid） ── */
.grid { display: grid; grid-template-columns: repeat(var(--grid-cols, 2), minmax(0, 1fr)); gap: var(--grid-gap); align-items: start; }
.grid-cell { min-width: 0; }
.grid .block { margin-bottom: 0; }

/* ── 提示条 ── */
.note {
  display: block;
  padding: 11px 14px;
  border-left: 3px solid var(--note-bar);
  border-radius: 8px;
  background: var(--note-bg);
  color: var(--card-fg);
}

/* ── 页码条 ── */
.card-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 7px 13px;
  border: 1px solid var(--pager-border);
  border-radius: 999px;
  background: var(--pager-bg);
  font-size: var(--muted-size);
  color: var(--card-muted);
}
.pager-page { font-weight: 700; letter-spacing: 0.04em; color: var(--accent); }
.pager-sep { opacity: 0.45; }
.pager-dots { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.pager-dot { width: 6px; height: 6px; border-radius: 999px; background: var(--card-muted); opacity: 0.35; }
.pager-dot.is-current { width: 16px; border-radius: 999px; background: var(--accent); opacity: 1; }

/* ── 空态与页脚 ── */
.empty, td.empty { color: var(--card-muted); }
td.empty { text-align: center; padding: 14px 8px; }
.block--empty .empty { display: block; text-align: center; padding: 12px 0; }
.card-footer {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 15px;
  padding-top: 11px;
  border-top: 1px solid var(--hairline);
  font-size: var(--muted-size);
  letter-spacing: 0.03em;
  color: var(--card-muted);
}
.card-footer::before {
  content: "";
  flex: 0 0 auto;
  width: 16px;
  height: 2px;
  border-radius: 2px;
  background: var(--head-rule);
}
"""


# ----------------------------------------------------------------------
# 块渲染（所有文本一律 escape 后进文本节点）
# ----------------------------------------------------------------------


def _escape(value: Any) -> str:
    return html_module.escape(str(value if value is not None else ""), quote=True)


def _tone(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _TONES else ""


def _variant(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if _VARIANT_NAME.fullmatch(name) else ""


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _escape_cell(cell: Any) -> str:
    """单元格：标量 escape 后直出；映射可带 tone / mono / chip；序列按多行堆叠。"""
    if isinstance(cell, Mapping):
        tone = _tone(cell.get("tone"))
        classes = ["cell"]
        if tone:
            classes.append(f"cell--{tone}")
        if cell.get("mono"):
            classes.append("cell--mono")
        if cell.get("chip"):
            classes.append("cell--chip")
        text = cell.get("text", cell.get("value", ""))
        return f'<span class="{" ".join(classes)}">{_escape(text)}</span>'
    if isinstance(cell, Sequence) and not isinstance(cell, (str, bytes)):
        lines = "".join(f'<span class="cell-line">{_escape(item)}</span>' for item in cell)
        return lines or '<span class="cell-line"></span>'
    return _escape(cell)


def _row_cells(row: Any) -> list[Any]:
    if isinstance(row, Mapping):
        return list(row.values())
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        return list(row)
    return []


def _width_values(value: Any) -> list[str]:
    """列宽（colgroup）：只接受 NN% / NNpx 形式，非法值忽略。"""
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    widths: list[str] = []
    for item in value:
        text = str(item).strip()
        widths.append(text if _WIDTH_VALUE.fullmatch(text) else "")
    return widths


def _colgroup(widths: Sequence[str]) -> str:
    if not widths or not any(widths):
        return ""
    cols = "".join(f'<col style="width: {width}">' if width else "<col>" for width in widths)
    return f"<colgroup>{cols}</colgroup>"


def _subheading(block: Mapping[str, Any]) -> str:
    title = block.get("title")
    return f'<h3 class="block-subheading">{_escape(title)}</h3>' if title else ""


def _kv_rows(items: Any) -> str:
    rows: list[str] = []
    for item in items or ():
        if isinstance(item, Mapping):
            label = item.get("label", item.get("key", ""))
            value = item.get("value", "")
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
            label, value = item[0], item[1]
        else:
            continue
        rows.append(f"<tr><th>{_escape(label)}</th><td>{_escape_cell(value)}</td></tr>")
    if not rows:
        rows.append('<tr><td class="empty" colspan="2">暂无数据</td></tr>')
    return "".join(rows)


def _rows_table(block: Mapping[str, Any]) -> str:
    columns = [str(column) for column in (block.get("columns") or ())]
    widths = _width_values(block.get("widths"))
    head = (
        "<thead><tr>"
        + "".join(f"<th>{_escape(column)}</th>" for column in columns)
        + "</tr></thead>"
        if columns
        else ""
    )
    body_rows: list[str] = []
    for row in block.get("rows") or ():
        cells = _row_cells(row)
        if not cells:
            continue
        body_rows.append(
            "<tr>" + "".join(f"<td>{_escape_cell(cell)}</td>" for cell in cells) + "</tr>"
        )
    if not body_rows:
        span = max(1, len(columns))
        body_rows.append(f'<tr><td class="empty" colspan="{span}">暂无数据</td></tr>')
    return f"{_colgroup(widths)}{head}<tbody>{''.join(body_rows)}</tbody>"


def _stats_grid(items: Any) -> str:
    tiles: list[str] = []
    for item in items or ():
        if isinstance(item, Mapping):
            label = item.get("label", item.get("key", ""))
            value = item.get("value", "")
            tone = _tone(item.get("tone"))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
            label, value = item[0], item[1]
            tone = _tone(item[2]) if len(item) >= 3 else ""
        else:
            continue
        classes = "stat" + (f" stat--{tone}" if tone else "")
        tiles.append(
            f'<div class="{classes}">'
            f'<span class="stat-label">{_escape(label)}</span>'
            f'<span class="stat-value">{_escape_cell(value)}</span>'
            "</div>"
        )
    return f'<div class="stats">{"".join(tiles)}</div>' if tiles else ""


def _pager_strip(block: Mapping[str, Any]) -> str:
    pages = max(1, _safe_int(block.get("pages"), 1))
    page = min(max(_safe_int(block.get("page"), 1), 1), pages)
    dots = ""
    if 1 < pages <= 10:
        dots = "".join(
            f'<i class="pager-dot{" is-current" if index == page else ""}"></i>'
            for index in range(1, pages + 1)
        )
    hint = block.get("hint")
    hint_html = f'<span class="pager-sep">·</span><span>{_escape(hint)}</span>' if hint else ""
    return (
        '<div class="card-pager">'
        f'<span class="pager-page">第 {page}/{pages} 页</span>'
        f"{hint_html}"
        f'<span class="pager-dots">{dots}</span>'
        "</div>"
    )


def _render_blocks(blocks: Any) -> str:
    return "\n".join(
        part for part in (_render_block(block) for block in (blocks or ())) if part
    )


def _render_block(block: Any) -> str:
    """渲染单个块：heading / kv / rows / stats / grid / note / pager / slot / marker。"""
    if not isinstance(block, Mapping):
        return ""
    kind = str(block.get("kind") or "").strip().lower()
    tone = _tone(block.get("tone"))
    variant = _variant(block.get("variant"))
    base = f"block--{kind or 'empty'}"
    classes = ["block", base]
    if tone:
        classes.append(f"tone-{tone}")
    if variant:
        classes.append(f"variant-{variant}")
    inner = ""

    if kind == "heading":
        inner = f'<h2 class="block-heading">{_escape(block.get("text"))}</h2>'
    elif kind == "note":
        inner = f'<div class="note">{_escape(block.get("text"))}</div>'
    elif kind == "kv":
        items = block.get("items")
        if items is None:
            items = block.get("rows")
        inner = f'{_subheading(block)}<table class="kv">{_kv_rows(items)}</table>'
    elif kind in ("rows", "table"):
        table_classes = "rows" + (f" rows--{variant}" if variant else "")
        classes[1] = "block--rows"
        inner = f'{_subheading(block)}<table class="{table_classes}">{_rows_table(block)}</table>'
    elif kind == "stats":
        cols = min(max(_safe_int(block.get("cols"), 3), 1), 4)
        inner = (
            f'{_subheading(block)}'
            f'<div class="stats-wrap" style="--stat-cols: {cols}">'
            f'{_stats_grid(block.get("items"))}</div>'
        )
    elif kind == "grid":
        cols = min(max(_safe_int(block.get("cols"), 2), 1), 4)
        cells = "".join(
            f'<div class="grid-cell">{_render_blocks(cell)}</div>'
            for cell in (block.get("cells") or ())
        )
        inner = f'<div class="grid" style="--grid-cols: {cols}">{cells}</div>'
    elif kind == "pager":
        inner = _pager_strip(block)
    elif kind == "slot":
        name = str(block.get("name") or "").strip().lower()
        if not _SLOT_NAME.fullmatch(name):
            logger.warning(f"非法插槽名，已忽略: {block.get('name')!r}")
            return ""
        return (
            f'<div class="block block--slot card-slot" data-slot="{name}">'
            f"<!--slot:{name}--></div>"
        )
    elif kind == "marker":
        text = str(block.get("text") or "").strip()
        if not _MARKER_NAME.fullmatch(text):
            logger.warning(f"非法标记名，已忽略: {block.get('text')!r}")
            return ""
        return f'<div class="block block--marker card-marker" data-marker="{text}">{text}</div>'
    else:
        return ""
    return f'<div class="{" ".join(classes)}">{inner}</div>'


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
            if wait and not use_wait:
                logger.warning(
                    f"内嵌字体校验未通过，已改为不等字体直接渲染（字形仍由端口内联）: {exc}"
                )
            continue
        data = getattr(result, "data", None)
        if not data:
            logger.warning("卡片渲染未返回渲染数据，已降级")
            return None
        return bytes(data)
    logger.warning(f"卡片渲染失败，已降级: {last_error}")
    return None


__all__ = [
    "BUILTIN_THEMES",
    "CARD_SELECTOR",
    "DEFAULT_WIDTH",
    "EmbeddedFont",
    "FONT_META_NAME",
    "THEMES",
    "THEME_NAMES",
    "THEME_SPECS",
    "ThemeFont",
    "ThemeRegistrationError",
    "ThemeSpec",
    "card_fonts",
    "get_screenshots",
    "get_theme",
    "has_slot",
    "inject_marker",
    "inject_slot",
    "register_theme",
    "registered_themes",
    "render_card_html",
    "render_card_image",
    "resolve_theme",
    "set_screenshots",
    "slot_placeholder",
    "svg_data_uri",
    "theme_css",
    "theme_spec",
    "theme_svg",
    "theme_variables",
    "unregister_theme",
]
