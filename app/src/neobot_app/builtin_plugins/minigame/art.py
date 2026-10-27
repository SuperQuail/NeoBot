"""四个玩法卡片的专属美术片段（全部由插件自己用 SVG 画出来）。

安全边界：片段只由**模块常量 + 程序产出的数字**拼成，不含任何用户输入；
用户文本一律先经渲染器的 escape → Markdown → URL 清洗，才进入卡片正文。
片段里没有外链、没有 script、没有事件处理器，因此可以安全地用 inject_slot 注入。

每个片段自带一段内联 style（类名统一前缀 mg-*），颜色尽量引用主题变量
（--accent / --panel-bg / --panel-border），这样同一份美术在「玩法艺术主题」
与「minecraft 主题」下都协调。
"""

from __future__ import annotations

from .parts.art_common import _style as _style
from .parts.art_bottle import BOTTLE_CSS, bottle_scene, bottle_avatar, bottle_note
from .parts.art_chengyu import CHENGYU_CSS, chengyu_scroll, chengyu_progress
from .parts.art_checkin import (
    CHECKIN_CSS,
    _calendar_page as _calendar_page,
    _stamp_mark as _stamp_mark,
    checkin_art,
)
from .parts.art_fortune import (
    FORTUNE_PALETTE,
    FORTUNE_FALLBACK as FORTUNE_FALLBACK,
    FORTUNE_LABELS,
    WEEKDAYS,
    safe_level_label,
    FORTUNE_CSS,
    _fortune_stick_svg as _fortune_stick_svg,
    fortune_art,
)


__all__ = [
    "BOTTLE_CSS",
    "CHECKIN_CSS",
    "CHENGYU_CSS",
    "FORTUNE_CSS",
    "FORTUNE_LABELS",
    "FORTUNE_PALETTE",
    "WEEKDAYS",
    "bottle_avatar",
    "bottle_note",
    "bottle_scene",
    "checkin_art",
    "chengyu_progress",
    "chengyu_scroll",
    "fortune_art",
    "safe_level_label",
]
