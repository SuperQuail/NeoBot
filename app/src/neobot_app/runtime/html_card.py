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

from neobot_app.utils.logger import get_module_logger

from .html_parts.base import (
    BUILTIN_THEMES,
    CARD_SELECTOR,
    DEFAULT_WIDTH,
    FONT_META_NAME,
    THEMES,
    THEME_NAMES,
    THEME_SPECS,
    EmbeddedFont,
    ThemeFont,
    ThemeRegistrationError,
    ThemeSpec,
)
from .html_parts.builtin_themes import _install_builtin_themes
from .html_parts.render import (
    get_screenshots,
    has_slot,
    inject_marker,
    inject_slot,
    render_card_html,
    render_card_image,
    set_screenshots,
    slot_placeholder,
)
from .html_parts.theme_registry import (
    card_fonts,
    get_theme,
    register_theme,
    registered_themes,
    resolve_theme,
    theme_css,
    theme_spec,
    theme_svg,
    theme_variables,
    unregister_theme,
)
from .html_parts.theme_validation import svg_data_uri

logger = get_module_logger("runtime.html_card")

# 内置主题在门面导入时注册，与插件主题走同一条校验路径。
_install_builtin_themes()

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
