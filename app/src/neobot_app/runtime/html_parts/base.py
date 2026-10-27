"""主题模型与渲染常量：主题声明、内置主题名、转义/自包含校验的共用常量。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from neobot_contracts.ports.screenshot import FontFace

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

