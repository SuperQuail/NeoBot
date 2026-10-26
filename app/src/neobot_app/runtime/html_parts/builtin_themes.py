"""四套内置主题的声明数据与注册入口。"""

from __future__ import annotations

from typing import Any

from .base import BUILTIN_THEMES
from .theme_registry import register_theme

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
