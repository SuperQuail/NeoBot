"""小游戏卡片主题：Minecraft 像素主题 + 各玩法的专属美术主题与候选池。

本模块只做三件事：

1. 用渲染器公开的 register_theme 注册**本插件自己的**三套主题：
   minecraft（像素泥土背景 / 3D 凸起边框 / 内嵌 Monocraft + FusionPixel）、
   chengyu（宣纸卷轴）、checkin（日历打卡）；
2. 声明**每个玩法的候选主题池**（含 minecraft 与该玩法的专属艺术主题）；
3. 提供「本次卡片用哪个主题」的选择函数（random 按玩法候选池随机 /
   fixed 固定），并把结果交给调用方记日志。

内置主题（default / bottle / game / fortune）由渲染器自己注册，这里只把它们算进
「已知主题名」，**不重复注册**，也**绝不注销**它们。
"""

from __future__ import annotations

from typing import Any

from neobot_app.runtime.html_card import (
    EmbeddedFont,
    register_theme,
    unregister_theme,
    svg_data_uri,
)

#: 渲染器内置主题 id（已知主题名的一部分，不由本插件注册）
BUILTIN_THEME_IDS: tuple[str, ...] = ("default", "bottle", "game", "fortune")

#: 本插件注册的主题 id
MINECRAFT_THEME = "minecraft"
CHENGYU_THEME = "chengyu"
CHECKIN_THEME = "checkin"

#: 本插件注册的全部主题（卸载时逐个注销）
PLUGIN_THEMES: tuple[str, ...] = (MINECRAFT_THEME, CHENGYU_THEME, CHECKIN_THEME)

#: 配置校验允许的主题名（内置 + 本插件）
KNOWN_THEME_IDS: tuple[str, ...] = BUILTIN_THEME_IDS + PLUGIN_THEMES

#: 主题模式：按玩法候选池随机 / 固定一个主题
THEME_MODES: tuple[str, ...] = ("random", "fixed")

#: 每个玩法的候选主题池（random 模式下从中随机；第一个是 fixed 留空时的默认主题）
GAME_THEME_POOLS: dict[str, tuple[str, ...]] = {
    "bottle": ("bottle", MINECRAFT_THEME),
    "chengyu": (CHENGYU_THEME, MINECRAFT_THEME),
    "checkin": (CHECKIN_THEME, MINECRAFT_THEME),
    "fortune": ("fortune", MINECRAFT_THEME),
}

#: 字体目录（随插件分发；缺失只 warning，渲染回落系统字体）
FONT_DIR = "assets/fonts"

#: 像素字体栈：拉丁字形走 Monocraft，中文靠 FusionPixel 逐字形回退，最后等宽兜底
MONOCRAFT_FONT_STACK: tuple[str, ...] = (
    '"Monocraft"',
    '"FusionPixel"',
    '"Microsoft YaHei"',
    "monospace",
)


# ----------------------------------------------------------------------
# Minecraft：像素泥土 / 草皮 / 石块
# ----------------------------------------------------------------------

#: 泥土平铺图块（16x16 整数像素，含亮暗噪点；crispEdges 保证放大后依然是硬边）
MC_DIRT_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"'
    ' shape-rendering="crispEdges">'
    '<rect width="16" height="16" fill="#4a3722"/>'
    '<g fill="#3c2c1a">'
    '<rect x="1" y="2" width="2" height="2"/><rect x="5" y="1" width="1" height="1"/>'
    '<rect x="9" y="3" width="2" height="1"/><rect x="13" y="1" width="2" height="2"/>'
    '<rect x="3" y="6" width="1" height="1"/><rect x="7" y="5" width="2" height="2"/>'
    '<rect x="12" y="7" width="2" height="1"/><rect x="1" y="9" width="2" height="1"/>'
    '<rect x="6" y="10" width="1" height="2"/><rect x="10" y="9" width="2" height="2"/>'
    '<rect x="14" y="11" width="2" height="1"/><rect x="2" y="13" width="2" height="2"/>'
    '<rect x="8" y="13" width="1" height="1"/><rect x="12" y="14" width="2" height="1"/>'
    "</g>"
    '<g fill="#5c452b">'
    '<rect x="3" y="1" width="2" height="1"/><rect x="7" y="2" width="1" height="1"/>'
    '<rect x="11" y="2" width="2" height="1"/><rect x="0" y="5" width="2" height="1"/>'
    '<rect x="4" y="4" width="1" height="1"/><rect x="10" y="5" width="1" height="1"/>'
    '<rect x="14" y="4" width="2" height="2"/><rect x="2" y="8" width="1" height="1"/>'
    '<rect x="5" y="8" width="2" height="1"/><rect x="9" y="7" width="1" height="1"/>'
    '<rect x="12" y="9" width="1" height="1"/><rect x="0" y="11" width="1" height="1"/>'
    '<rect x="4" y="11" width="2" height="2"/><rect x="8" y="11" width="1" height="1"/>'
    '<rect x="13" y="12" width="2" height="1"/><rect x="6" y="14" width="2" height="1"/>'
    '<rect x="10" y="15" width="2" height="1"/>'
    "</g>"
    '<g fill="#6d5233">'
    '<rect x="5" y="3" width="1" height="1"/><rect x="12" y="5" width="1" height="1"/>'
    '<rect x="3" y="12" width="1" height="1"/><rect x="9" y="12" width="1" height="1"/>'
    "</g>"
    "</svg>"
)

#: 草皮 + 石块底纹（卡片内底纹：顶部草皮条 + 右下石块 + 零散亮暗噪点）
MC_ORNAMENT = (
    '<svg class="nb-decor nb-mc" width="100%" height="100%" aria-hidden="true"'
    ' shape-rendering="crispEdges">'
    "<defs>"
    '<pattern id="nbMcGrass" width="16" height="16" patternUnits="userSpaceOnUse">'
    '<rect x="0" y="0" width="16" height="4" fill="#5f9c3c"/>'
    '<rect x="0" y="0" width="16" height="2" fill="#79bd4c"/>'
    '<rect x="1" y="4" width="2" height="2" fill="#5f9c3c"/>'
    '<rect x="6" y="4" width="1" height="2" fill="#5f9c3c"/>'
    '<rect x="10" y="4" width="3" height="1" fill="#5f9c3c"/>'
    '<rect x="14" y="4" width="2" height="2" fill="#5f9c3c"/>'
    '<rect x="3" y="0" width="1" height="1" fill="#a2dc63"/>'
    '<rect x="9" y="0" width="2" height="1" fill="#a2dc63"/>'
    '<rect x="12" y="1" width="1" height="1" fill="#3f6b26"/>'
    "</pattern>"
    "</defs>"
    '<rect x="0" y="0" width="100%" height="18" fill="url(#nbMcGrass)"/>'
    '<g transform="translate(-58 -52)">'
    '<rect x="100%" y="100%" width="22" height="22" fill="#6d6d6d"/>'
    '<rect x="100%" y="100%" width="22" height="6" fill="#8b8b8b"/>'
    '<rect x="100%" y="100%" width="6" height="22" fill="#8b8b8b"/>'
    '<rect x="100%" y="100%" width="22" height="5" fill="#3f3f3f" transform="translate(0 17)"/>'
    '<rect x="100%" y="100%" width="5" height="22" fill="#3f3f3f" transform="translate(17 0)"/>'
    '<rect x="100%" y="100%" width="8" height="8" fill="#5a5a5a" transform="translate(-14 6)"/>'
    '<rect x="100%" y="100%" width="6" height="6" fill="#7c7c7c" transform="translate(-12 8)"/>'
    "</g>"
    '<g transform="translate(-26 -26)">'
    '<rect x="100%" y="100%" width="10" height="10" fill="#5f9c3c"/>'
    '<rect x="100%" y="100%" width="10" height="3" fill="#79bd4c"/>'
    "</g>"
    '<g fill="#8a6a44" opacity="0.55">'
    '<rect x="6%" y="26%" width="3" height="3"/><rect x="18%" y="12%" width="2" height="2"/>'
    '<rect x="31%" y="34%" width="3" height="3"/><rect x="44%" y="19%" width="2" height="2"/>'
    '<rect x="57%" y="30%" width="3" height="3"/><rect x="70%" y="15%" width="2" height="2"/>'
    '<rect x="83%" y="36%" width="3" height="3"/><rect x="92%" y="22%" width="2" height="2"/>'
    "</g>"
    '<g fill="#241a10" opacity="0.45">'
    '<rect x="12%" y="44%" width="3" height="3"/><rect x="26%" y="58%" width="2" height="2"/>'
    '<rect x="38%" y="48%" width="3" height="3"/><rect x="52%" y="66%" width="2" height="2"/>'
    '<rect x="64%" y="52%" width="3" height="3"/><rect x="76%" y="70%" width="2" height="2"/>'
    '<rect x="88%" y="58%" width="3" height="3"/><rect x="8%" y="76%" width="2" height="2"/>'
    "</g>"
    "</svg>"
)

#: 标题右侧徽章：苦力怕脸（像素方块，currentColor = --accent）
MC_EMBLEM = (
    '<svg viewBox="0 0 36 36" width="100%" height="100%" shape-rendering="crispEdges">'
    '<rect x="2" y="2" width="32" height="32" fill="currentColor" opacity="0.92"/>'
    '<rect x="2" y="2" width="32" height="4" fill="#ffffff" opacity="0.16"/>'
    '<g fill="#151b0f">'
    '<rect x="7" y="9" width="8" height="8"/><rect x="21" y="9" width="8" height="8"/>'
    '<rect x="15" y="17" width="6" height="6"/>'
    '<rect x="11" y="23" width="6" height="6"/><rect x="19" y="23" width="6" height="6"/>'
    '<rect x="14" y="25" width="8" height="4"/>'
    "</g>"
    "</svg>"
)

#: 主题专属 CSS（平铺尺寸写在这里，不写进 variables —— 变量是主题缺省值，会泄漏给别的主题）
MC_CSS = """\
.card-veil { background-size: 48px 48px, 100% 100%; background-repeat: repeat, no-repeat; }
/* 像素字体必须整数倍字号（8px 网格：16 / 24 / 32px），否则边缘会被抗锯齿糊掉 */
.card-subtitle, .block-subheading, .stat-label, .rows thead th, .card-footer, .card-pager,
.note, .cell--chip, .rows--commands { font-size: 16px; }
.rows--commands thead th, .rows--commands tbody td:last-child { font-size: 16px; }
.block-heading::before { width: 8px; border-radius: 0; }
.card-head::after { height: 4px; border-radius: 0; }
.block--kv, .block--rows, .block--stats .stat {
  box-shadow: inset 3px 3px 0 rgba(255, 255, 255, 0.20), inset -3px -3px 0 rgba(0, 0, 0, 0.58);
}
.note { border-radius: 0; border-left-width: 6px; }
.card-pager, .pager-dot, .pager-dot.is-current, .cell--chip { border-radius: 0; }
.card-emblem { filter: drop-shadow(3px 3px 0 rgba(0, 0, 0, 0.65)); }
.mg-md pre { background: rgba(0, 0, 0, 0.45); border-radius: 0; }
"""


# ----------------------------------------------------------------------
# 成语接龙：宣纸 + 卷轴 + 朱砂
# ----------------------------------------------------------------------

#: 宣纸纤维底纹（很淡的横竖纤维 + 少量杂点）
CHENGYU_PAPER_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
    '<rect width="24" height="24" fill="#fbf5e6"/>'
    '<g stroke="#e6d9bb" stroke-width="1" opacity="0.7">'
    '<path d="M0 5h24"/><path d="M0 17h24"/>'
    '<path d="M7 0v24"/><path d="M19 0v24"/>'
    "</g>"
    '<g fill="#efe2c4">'
    '<rect x="2" y="9" width="4" height="1"/><rect x="12" y="2" width="3" height="1"/>'
    '<rect x="17" y="13" width="5" height="1"/><rect x="5" y="20" width="4" height="1"/>'
    '<rect x="20" y="8" width="2" height="1"/><rect x="9" y="15" width="3" height="1"/>'
    "</g>"
    '<g fill="#f2e6cc" opacity="0.8">'
    '<rect x="0" y="0" width="2" height="2"/><rect x="22" y="22" width="2" height="2"/>'
    "</g>"
    "</svg>"
)

#: 宣纸底纹：回纹边框 + 淡墨笔触
CHENGYU_ORNAMENT = (
    '<svg class="nb-decor nb-chengyu" width="100%" height="100%" aria-hidden="true">'
    "<defs>"
    '<pattern id="nbCyMeander" width="26" height="26" patternUnits="userSpaceOnUse">'
    '<path d="M5 21V5h16v12H9V9h8" fill="none" stroke="rgba(140, 46, 36, 0.10)"'
    ' stroke-width="1.4"/></pattern>'
    "</defs>"
    '<rect width="100%" height="100%" fill="url(#nbCyMeander)"/>'
    '<g fill="rgba(58, 44, 28, 0.07)">'
    '<path d="M28 96c34-26 62 12 96-6s58-30 92-10 62 26 96 6 58-24 92-6 62 22 96 6v14c-34 16-62-2-96-8s-58 4-92 12-62-2-96-10-58 6-92 12-62-2-96-10z"/>'
    "</g>"
    '<g stroke="rgba(58, 44, 28, 0.06)" stroke-width="2" fill="none">'
    '<path d="M40 130c60-24 120 18 180-4s120-30 180-8 120 26 180 4"/>'
    "</g>"
    '<rect x="0" y="0" width="100%" height="100%" fill="none" stroke="rgba(140, 46, 36, 0.16)"'
    ' stroke-width="6"/>'
    "</svg>"
)

#: 徽章：朱砂方印「接」
CHENGYU_EMBLEM = (
    '<svg viewBox="0 0 40 40" width="100%" height="100%">'
    '<rect x="4" y="4" width="32" height="32" rx="3" fill="none" stroke="currentColor"'
    ' stroke-width="3"/>'
    '<g fill="currentColor" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif"'
    ' font-size="20" text-anchor="middle">'
    '<text x="20" y="28">\u63a5</text>'
    "</g></svg>"
)

CHENGYU_CSS = """\
.card-veil { background-size: 72px 72px, 100% 100%; background-repeat: repeat, no-repeat; }
.card-head::after { height: 3px; }
.block-heading::before { width: 5px; border-radius: 1px; }
.card-footer::before { background: var(--head-rule); }
"""

#: 主题变量（卷轴 / 宣纸）
CHENGYU_PACK: dict[str, Any] = {
    "font_stack": (
        '"Kaiti SC", "KaiTi", "STKaiti", "Songti SC", "SimSun", "Noto Serif SC", serif'
    ),
    "variables": {
        "--card-bg": "linear-gradient(172deg, #fdf8ea 0%, #f6edd6 52%, #ecdcbb 100%)",
        "--card-fg": "#3b2c1a",
        "--card-muted": "#8a7350",
        "--accent": "#a8352a",
        "--radius": "8px",
        "--card-border": "#d8c39a",
        "--card-border-width": "2px",
        "--card-pad": "22px 24px 20px",
        "--card-shadow": "0 14px 32px rgba(96, 64, 20, 0.22)",
        "--panel-bg": "rgba(255, 255, 255, 0.60)",
        "--panel-border": "#e3d2ac",
        "--panel-radius": "4px",
        "--panel-pad": "13px 15px",
        "--panel-shadow": "inset 0 0 0 1px rgba(255, 255, 255, 0.70)",
        "--tile-bg": "rgba(168, 53, 42, 0.05)",
        "--tile-radius": "3px",
        "--hairline": "#e2d0a8",
        "--zebra": "rgba(168, 53, 42, 0.045)",
        "--table-head-bg": "rgba(168, 53, 42, 0.07)",
        "--title-font": '"Kaiti SC", "KaiTi", "STKaiti", "Songti SC", serif',
        "--title-size": "26px",
        "--title-weight": "700",
        "--title-tracking": "0.08em",
        "--title-color": "#70251a",
        "--title-shadow": "0 1px 0 rgba(255, 255, 255, 0.85)",
        "--head-rule": "linear-gradient(90deg, #a8352a, rgba(168, 53, 42, 0))",
        "--head-rule-width": "110px",
        "--heading-size": "16px",
        "--heading-color": "#8f3126",
        "--heading-tracking": "0.10em",
        "--accent-soft": "rgba(168, 53, 42, 0.12)",
        "--subheading-color": "#8a6a44",
        "--card-bg-image": (
            "radial-gradient(120% 70% at 50% -10%, rgba(255, 255, 255, 0.85),"
            " rgba(255, 255, 255, 0) 58%)"
        ),
    },
    "css": CHENGYU_CSS,
    "ornament": CHENGYU_ORNAMENT,
    "emblem": CHENGYU_EMBLEM,
    "svg_assets": {"paper": CHENGYU_PAPER_TILE},
}


# ----------------------------------------------------------------------
# 签到：日历 + 打卡印章
# ----------------------------------------------------------------------

#: 日历格纹底纹（淡格子 + 少量淡红块）
CHECKIN_GRID_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
    '<rect width="32" height="32" fill="#ffffff"/>'
    '<g stroke="rgba(120, 108, 92, 0.16)" stroke-width="1">'
    '<path d="M0 0h32"/><path d="M0 0v32"/>'
    "</g>"
    '<g fill="rgba(216, 67, 58, 0.05)">'
    '<rect x="1" y="1" width="14" height="14"/><rect x="17" y="17" width="14" height="14"/>'
    "</g>"
    "</svg>"
)

#: 日历元素：装订环 + 淡格纹 + 顶部红带
CHECKIN_ORNAMENT = (
    '<svg class="nb-decor nb-checkin" width="100%" height="100%" aria-hidden="true">'
    "<defs>"
    '<pattern id="nbCkGrid" width="34" height="34" patternUnits="userSpaceOnUse">'
    '<path d="M34 0H0v34" fill="none" stroke="rgba(130, 116, 98, 0.14)" stroke-width="1"/>'
    "</pattern>"
    "</defs>"
    '<rect width="100%" height="100%" fill="url(#nbCkGrid)"/>'
    '<rect x="0" y="0" width="100%" height="10" fill="rgba(216, 67, 58, 0.09)"/>'
    '<g fill="rgba(120, 108, 92, 0.35)">'
    '<rect x="26" y="0" width="6" height="14" rx="3"/>'
    '<rect x="46" y="0" width="6" height="14" rx="3"/>'
    '<rect x="66" y="0" width="6" height="14" rx="3"/>'
    "</g>"
    "</svg>"
)

#: 徽章：日历页 + 红色页眉 + 对勾
CHECKIN_EMBLEM = (
    '<svg viewBox="0 0 40 40" width="100%" height="100%">'
    '<rect x="5" y="6" width="30" height="29" rx="4" fill="none" stroke="currentColor"'
    ' stroke-width="2.6"/>'
    '<rect x="5" y="6" width="30" height="9" rx="4" fill="currentColor" opacity="0.85"/>'
    '<path d="M13 28l5 5 10-12" fill="none" stroke="currentColor" stroke-width="3.2"'
    ' stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)

CHECKIN_CSS = """\
.card-veil { background-size: 34px 34px, 100% 100%; background-repeat: repeat, no-repeat; }
.card-head { border-bottom-color: #e8e0d2; }
.block-heading::before { width: 6px; border-radius: 1px; }
.card-footer::before { background: var(--head-rule); }
.block--stats .stat--accent { border-color: rgba(216, 67, 58, 0.45); }
"""

#: 主题变量（日历 / 打卡）
CHECKIN_PACK: dict[str, Any] = {
    "variables": {
        "--card-bg": "linear-gradient(176deg, #ffffff 0%, #fbf8f2 58%, #f1ebdf 100%)",
        "--card-fg": "#3b3730",
        "--card-muted": "#8d8478",
        "--accent": "#d8433a",
        "--radius": "10px",
        "--card-border": "#e6dfd3",
        "--card-border-width": "2px",
        "--card-pad": "22px 24px 20px",
        "--card-shadow": "0 14px 32px rgba(70, 58, 38, 0.20)",
        "--panel-bg": "rgba(255, 255, 255, 0.78)",
        "--panel-border": "#e8e0d2",
        "--panel-radius": "8px",
        "--panel-pad": "13px 15px",
        "--panel-shadow": "inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 2px 6px rgba(70, 58, 38, 0.05)",
        "--tile-bg": "rgba(216, 67, 58, 0.05)",
        "--tile-radius": "8px",
        "--hairline": "#ece5d8",
        "--zebra": "rgba(216, 67, 58, 0.04)",
        "--table-head-bg": "rgba(216, 67, 58, 0.06)",
        "--title-size": "25px",
        "--title-weight": "800",
        "--title-tracking": "0.02em",
        "--title-color": "#8f2f28",
        "--title-shadow": "0 1px 0 rgba(255, 255, 255, 0.9)",
        "--head-rule": "linear-gradient(90deg, #d8433a, rgba(216, 67, 58, 0))",
        "--head-rule-width": "120px",
        "--heading-size": "15.5px",
        "--heading-color": "#c23a32",
        "--heading-tracking": "0.06em",
        "--accent-soft": "rgba(216, 67, 58, 0.12)",
        "--stat-value-size": "24px",
        "--card-bg-image": (
            "radial-gradient(120% 70% at 50% -12%, rgba(255, 255, 255, 0.95),"
            " rgba(255, 255, 255, 0) 60%)"
        ),
    },
    "css": CHECKIN_CSS,
    "ornament": CHECKIN_ORNAMENT,
    "emblem": CHECKIN_EMBLEM,
    "svg_assets": {"grid": CHECKIN_GRID_TILE},
}


# ----------------------------------------------------------------------
# Minecraft 主题包
# ----------------------------------------------------------------------

MINECRAFT_PACK: dict[str, Any] = {
    "variables": {
        "--card-bg": "#2b2117",
        "--card-fg": "#f2f2f2",
        "--card-muted": "#b6ada0",
        "--accent": "#7cc576",
        "--radius": "0px",
        "--card-border": "#161616",
        "--card-border-width": "4px",
        "--font-smoothing": "none",
        "--card-font-size": "16px",
        "--card-pad": "20px 22px 18px",
        "--card-shadow": (
            "inset 4px 4px 0 rgba(255, 255, 255, 0.26),"
            " inset -4px -4px 0 rgba(0, 0, 0, 0.62), 0 10px 26px rgba(0, 0, 0, 0.55)"
        ),
        "--panel-bg": "rgba(18, 15, 11, 0.74)",
        "--panel-border": "#8f8f8f",
        "--panel-radius": "0px",
        "--panel-pad": "12px 14px",
        "--panel-shadow": (
            "inset 2px 2px 0 rgba(255, 255, 255, 0.16),"
            " inset -2px -2px 0 rgba(0, 0, 0, 0.55)"
        ),
        "--tile-bg": "rgba(255, 255, 255, 0.07)",
        "--tile-radius": "0px",
        "--hairline": "rgba(180, 180, 180, 0.34)",
        "--zebra": "rgba(255, 255, 255, 0.05)",
        "--table-head-bg": "rgba(0, 0, 0, 0.42)",
        "--title-size": "24px",
        "--title-weight": "800",
        "--title-tracking": "0.02em",
        "--title-color": "#ffffff",
        "--title-shadow": "3px 3px 0 rgba(0, 0, 0, 0.85)",
        "--head-rule": (
            "repeating-linear-gradient(90deg, #7cc576 0 12px, rgba(124, 197, 118, 0) 12px 20px)"
        ),
        "--head-rule-width": "132px",
        "--heading-size": "16px",
        "--heading-color": "#a8e07a",
        "--heading-tracking": "0.06em",
        "--accent-soft": "rgba(124, 197, 118, 0.20)",
        "--stat-label-size": "16px",
        "--stat-value-size": "24px",
        "--table-font-size": "16px",
        "--muted-size": "16px",
        "--emblem-size": "42px",
    },
    "font_stack": MONOCRAFT_FONT_STACK,
    "embed_fonts": [
        EmbeddedFont("Monocraft", FONT_DIR + "/Monocraft-Regular.ttf"),
        EmbeddedFont("Monocraft", FONT_DIR + "/Monocraft-Bold.ttf", weight="700"),
        EmbeddedFont("FusionPixel", FONT_DIR + "/FusionPixel8px-zh_hans.woff2", format="woff2"),
    ],
    "background": (
        svg_data_uri(MC_DIRT_TILE)
        + ", linear-gradient(180deg, rgba(10, 9, 6, 0.46) 0%, rgba(9, 8, 6, 0.70) 58%,"
        " rgba(4, 4, 3, 0.82) 100%)"
    ),
    "css": MC_CSS,
    "ornament": MC_ORNAMENT,
    "emblem": MC_EMBLEM,
    "svg_assets": {"dirt": MC_DIRT_TILE},
}

#: 主题 id -> 主题包（注册时逐个走渲染器的自包含校验）
THEME_PACKS: dict[str, dict[str, Any]] = {
    MINECRAFT_THEME: MINECRAFT_PACK,
    CHENGYU_THEME: CHENGYU_PACK,
    CHECKIN_THEME: CHECKIN_PACK,
}


def register_minigame_themes() -> tuple[str, ...]:
    """注册本插件的三套主题（幂等：重复调用等价于覆盖）。

    相对字体路径以插件目录为基准；字体文件缺失只 warning（渲染回落系统字体），
    不会导致注册失败，更不会让插件起不来。
    """
    from pathlib import Path

    base_dir = Path(__file__).parent
    registered: list[str] = []
    for theme_id in PLUGIN_THEMES:
        pack = dict(THEME_PACKS[theme_id])
        if pack.get("embed_fonts"):
            pack["font_base_dir"] = base_dir
        register_theme(theme_id, replace=True, **pack)
        registered.append(theme_id)
    return tuple(registered)


def unregister_minigame_themes() -> tuple[str, ...]:
    """注销本插件的主题（内置主题不受影响，渲染器会拒绝注销它们）。"""
    removed: list[str] = []
    for theme_id in PLUGIN_THEMES:
        if unregister_theme(theme_id):
            removed.append(theme_id)
    return tuple(removed)


def is_registered(theme_id: str) -> bool:
    """主题当前是否已注册（不触发回落）。"""
    from neobot_app.runtime.html_card import THEME_SPECS

    return str(theme_id or "").strip().lower() in THEME_SPECS


def theme_pool(game_id: str) -> tuple[str, ...]:
    """玩法的候选主题池；未知玩法回落 default。"""
    return GAME_THEME_POOLS.get(str(game_id or "").strip(), ("default",))


def default_theme(game_id: str) -> str:
    """玩法的默认主题（fixed 模式且未指定 theme 时用它）。"""
    return theme_pool(game_id)[0]


def resolve_theme(game_id: str, *, mode: str, theme: str, rng: Any) -> str:
    """解析本次卡片主题。

    - fixed：用配置里的 theme；留空用该玩法的默认主题；
    - random：从该玩法的候选池里随机（只从**已注册**的主题里挑，
      因此插件主题缺失时不会挑到不存在的主题）；
    - 任何情况下都保证返回一个已注册的主题名。
    """
    name = str(game_id or "").strip()
    pick = str(theme or "").strip().lower()
    if str(mode or "random").strip().lower() == "fixed":
        candidate = pick or default_theme(name)
    else:
        pool = [item for item in theme_pool(name) if is_registered(item)]
        if not pool:
            pool = ["default"]
        index = int(rng.randrange(len(pool))) if len(pool) > 1 else 0
        candidate = pool[index]
    if not is_registered(candidate):
        return "default"
    return candidate


__all__ = [
    "BUILTIN_THEME_IDS",
    "CHECKIN_THEME",
    "CHENGYU_THEME",
    "GAME_THEME_POOLS",
    "KNOWN_THEME_IDS",
    "MINECRAFT_THEME",
    "MONOCRAFT_FONT_STACK",
    "PLUGIN_THEMES",
    "THEME_MODES",
    "THEME_PACKS",
    "default_theme",
    "is_registered",
    "register_minigame_themes",
    "resolve_theme",
    "theme_pool",
    "unregister_minigame_themes",
]
