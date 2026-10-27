"""抽签卡片美术：档位配色、签文 SVG 与整卡。"""

from __future__ import annotations

import html as html_module

from .art_common import _style


#: 抽签档位 -> 配色（签头切面色 / 签身渐变 / 印章色 / 光晕）
FORTUNE_PALETTE: dict[str, tuple[str, str, str, str, str]] = {
    # (cut, body_top, body_bottom, seal, glow)
    "great": ("#fff3c4", "#f0d276", "#c9a13a", "#b8231a", "rgba(255, 214, 102, 0.34)"),
    "good": ("#ffe9c9", "#e8bc72", "#bd8c39", "#b8231a", "rgba(232, 188, 114, 0.30)"),
    "middle": ("#dff3e6", "#8fc79f", "#5d946f", "#1f6b5c", "rgba(143, 199, 159, 0.26)"),
    "small": ("#e6f4d8", "#9dc46e", "#6d9440", "#2f6b2a", "rgba(157, 196, 110, 0.26)"),
    "flat": ("#eef0f2", "#b9bfc6", "#868d95", "#555c64", "rgba(185, 191, 198, 0.22)"),
    "small_bad": ("#e6e0f5", "#a99bcf", "#7568a6", "#4b3f7a", "rgba(169, 155, 207, 0.24)"),
    "bad": ("#dfe1e4", "#8b8f95", "#5c6067", "#33373d", "rgba(120, 124, 130, 0.22)"),
}

#: 兜底配色（未知档位）
FORTUNE_FALLBACK = FORTUNE_PALETTE["flat"]

#: 允许进入 SVG 的档位文字（只可能是程序常量；不在表里一律不画字）
FORTUNE_LABELS: tuple[str, ...] = ("大吉", "吉", "中吉", "小吉", "平", "小凶", "凶")

#: 星期一到星期日的中文
WEEKDAYS: tuple[str, ...] = ("一", "二", "三", "四", "五", "六", "日")

def safe_level_label(label: str) -> str:
    """只允许已知档位文字进入 SVG（防注入：任何其它值一律不画）。"""
    text = str(label or "").strip()
    return text if text in FORTUNE_LABELS else ""

# ----------------------------------------------------------------------
# 抽签：竹签（竹节 + 斜切签头 + 竖向艺术体文字）+ 签筒 + 签架
# ----------------------------------------------------------------------

FORTUNE_CSS = """\
.mgart-fortune { position: relative; margin: 0 0 14px; padding: 12px 10px 6px; border-radius: 10px;
  border: 1px solid var(--panel-border); background: var(--panel-bg); overflow: hidden; }
.mgart-fortune svg { display: block; width: 100%; height: auto; }
.mgart-fortune-cap { text-align: center; margin: 0 0 12px; font-size: 12.5px; letter-spacing: 0.28em;
  color: var(--card-muted); }
/* 内置 fortune 主题自带的竹签与「大吉」印章底纹：本卡片自己画了更大更专属的竹签，
   留着会与本卡的档位配色矛盾（例如「凶」签上盖一枚大吉印），所以在本卡内隐藏。 */
.nb-bamboo, .nb-seal { display: none; }
"""

def _fortune_stick_svg(*, label: str, key: str) -> str:
    cut, body_top, body_bottom, seal, glow = FORTUNE_PALETTE.get(
        str(key or "").strip(), FORTUNE_FALLBACK
    )
    chars = list(safe_level_label(label))
    size = 34 if len(chars) <= 2 else (26 if len(chars) == 3 else 22)
    start = 30 + (196 - size * len(chars) - (len(chars) - 1) * 8) / 2 if chars else 30
    texts: list[str] = []
    for index, char in enumerate(chars):
        y = start + size + index * (size + 6)
        texts.append(
            '<text x="160" y="' + str(round(y, 1)) + '">' + html_module.escape(char) + "</text>"
        )
    text_block = (
        '<g fill="#3d2a12" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif"'
        ' font-size="' + str(size) + '" text-anchor="middle" font-weight="bold">'
        + "".join(texts)
        + "</g>"
    )
    return (
        '<svg viewBox="0 0 320 330" aria-hidden="true">'
        "<defs>"
        '<linearGradient id="mgBamboo" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="' + body_bottom + '"/>'
        '<stop offset="0.38" stop-color="' + body_top + '"/>'
        '<stop offset="1" stop-color="' + body_bottom + '"/></linearGradient>'
        '<radialGradient id="mgGlow" cx="0.5" cy="0.5" r="0.5">'
        '<stop offset="0" stop-color="' + glow + '"/>'
        '<stop offset="1" stop-color="rgba(0, 0, 0, 0)"/></radialGradient>'
        "</defs>"
        '<circle cx="160" cy="150" r="132" fill="url(#mgGlow)"/>'
        # 签架
        '<g class="mgart-rack" fill="#6b4526">'
        '<rect x="34" y="286" width="252" height="14" rx="7"/>'
        '<rect x="46" y="252" width="14" height="42" rx="5"/>'
        '<rect x="260" y="252" width="14" height="42" rx="5"/>'
        "</g>"
        '<g fill="#9a6738">'
        '<rect x="34" y="286" width="252" height="5" rx="2.5"/>'
        '<rect x="46" y="252" width="14" height="6" rx="3"/>'
        '<rect x="260" y="252" width="14" height="6" rx="3"/>'
        "</g>"
        # 签筒（斜靠）
        '<g class="mgart-tube" transform="translate(252 216) rotate(14)">'
        '<rect x="-34" y="-70" width="68" height="140" rx="10" fill="url(#mgBamboo)"/>'
        '<rect x="-34" y="-70" width="68" height="140" rx="10" fill="none" stroke="'
        + body_bottom + '" stroke-width="2"/>'
        '<g fill="rgba(63, 92, 36, 0.35)">'
        '<rect x="-34" y="-30" width="68" height="7"/><rect x="-34" y="18" width="68" height="7"/>'
        "</g>"
        '<g fill="' + body_top + '" stroke="' + body_bottom + '" stroke-width="1.5">'
        '<rect x="-24" y="-96" width="12" height="34" rx="5"/>'
        '<rect x="-6" y="-104" width="12" height="42" rx="5"/>'
        '<rect x="12" y="-92" width="12" height="30" rx="5"/>'
        "</g>"
        "</g>"
        # 抽出的竹签
        '<g class="mgart-bamboo">'
        '<path d="M132 56L188 28v244a10 10 0 0 1-10 10h-36a10 10 0 0 1-10-10z"'
        ' fill="url(#mgBamboo)" stroke="' + body_bottom + '" stroke-width="2.4"/>'
        '<path d="M132 56l56-28v22l-56 28z" fill="' + cut + '" stroke="' + body_bottom
        + '" stroke-width="2.4"/>'
        '<g class="mgart-bamboo-node" stroke="rgba(63, 92, 36, 0.42)" stroke-width="5"'
        ' stroke-linecap="round">'
        '<path d="M132 106h56"/><path d="M132 166h56"/><path d="M132 226h56"/>'
        "</g>"
        '<g stroke="rgba(255, 255, 255, 0.30)" stroke-width="3" stroke-linecap="round">'
        '<path d="M138 62v214"/></g>'
        + text_block
        + '<g transform="translate(160 262)">'
        '<rect x="-30" y="-13" width="60" height="26" rx="4" fill="' + seal
        + '" opacity="0.92"/>'
        '<g fill="#fff4ec" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif"'
        ' font-size="17" text-anchor="middle"><text x="0" y="6">\u7b7e</text></g>'
        "</g>"
        '<path d="M140 272c-14 12-22 24-24 34" fill="none" stroke="#b8231a"'
        ' stroke-width="4" stroke-linecap="round"/>'
        '<path d="M180 272c14 12 22 24 24 34" fill="none" stroke="#b8231a"'
        ' stroke-width="4" stroke-linecap="round"/>'
        "</g>"
        "</svg>"
    )

def fortune_art(*, label: str, key: str, caption: str) -> str:
    """抽签卡片美术：竹签 + 签筒 + 签架 + 按档位配色。"""
    safe_caption = str(caption or "").strip()
    cap = (
        '<div class="mgart-fortune-cap">' + html_module.escape(safe_caption) + "</div>"
        if safe_caption
        else ""
    )
    return (
        '<div class="mgart-fortune">'
        + cap
        + _fortune_stick_svg(label=label, key=key)
        + "</div>"
        + _style(FORTUNE_CSS)
    )
