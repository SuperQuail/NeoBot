"""漂流瓶卡片美术：瓶身、头像与正文片段。"""

from __future__ import annotations

import html as html_module

from .art_common import _style


# ----------------------------------------------------------------------
# 漂流瓶：日/夜海面 + 玻璃瓶 + 沙滩
# ----------------------------------------------------------------------

BOTTLE_CSS = """\
.mgart-sea { position: relative; margin: 0 0 14px; border-radius: 14px; overflow: hidden;
  border: 1px solid var(--panel-border); background: rgba(8, 24, 40, 0.28); }
.mgart-sea svg { display: block; width: 100%; height: auto; }
.mgart-badge { position: absolute; left: 12px; top: 12px; display: inline-flex; align-items: center;
  gap: 6px; padding: 4px 10px; border-radius: 999px; font-size: 12.5px; letter-spacing: 0.06em;
  background: rgba(6, 14, 24, 0.62); color: #eaf6ff; border: 1px solid rgba(180, 225, 255, 0.35); }
.mgart-badge svg { width: 14px; height: 14px; }
.mgart-who { display: flex; align-items: center; gap: 14px; margin: 0 0 14px; padding: 10px 14px;
  border: 1px solid var(--panel-border); border-radius: 12px; background: var(--panel-bg); }
.mgart-port { position: relative; flex: 0 0 auto; border-radius: 50%; padding: 3px;
  background: var(--accent); box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.28); }
.mgart-who-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mgart-who-cap { font-size: 11.5px; letter-spacing: 0.16em; color: var(--card-muted); }
.mgart-who-name { font-size: 17px; font-weight: 700; color: var(--card-fg); overflow-wrap: anywhere; }
.mgart-note { position: relative; margin: 0 0 14px; padding: 16px 20px 16px 26px; color: #3a2f22;
  background: linear-gradient(158deg, #fdf7e6 0%, #f3e6c8 100%);
  box-shadow: inset 0 0 0 1px rgba(150, 118, 66, 0.30), 0 8px 20px rgba(6, 20, 32, 0.22); }
.mgart-note::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 8px;
  background: repeating-linear-gradient(180deg, #d9b877 0 8px, #c8a463 8px 16px); opacity: 0.9; }
.mgart-note::after { content: ""; position: absolute; right: 0; bottom: 0; width: 0; height: 0;
  border-left: 20px solid transparent; border-bottom: 20px solid rgba(150, 118, 66, 0.38); }
.mgart-note .mg-md { color: #3a2f22; }
.mgart-note .mg-md a { color: #9a4a1e; }
.mgart-note .mg-md pre { background: rgba(120, 92, 46, 0.14); color: #33291c; }
.mgart-note .mg-md code { color: #7a4a12; }
.mgart-note .mg-md blockquote { border-left-color: #b98b4a; color: #5b4a30; }
.mgart-grain { position: absolute; inset: 0; pointer-events: none; opacity: 0.35;
  background-image: repeating-linear-gradient(0deg, rgba(150, 118, 66, 0.16) 0 1px, transparent 1px 7px); }
"""

def bottle_scene(*, anonymous: bool) -> str:
    """漂流瓶卡片的「海面场景」：白天（普通）/ 夜晚（匿名）两套配色。"""
    if anonymous:
        sky_a, sky_b = "rgba(24, 30, 58, 0.62)", "rgba(10, 16, 34, 0.10)"
        orb, orb_op = "#e6ecff", "0.88"
        sea_back, sea_front = "rgba(58, 108, 168, 0.42)", "rgba(34, 74, 128, 0.55)"
        sand = "rgba(196, 178, 150, 0.42)"
        stars = (
            '<g fill="#eaf1ff" opacity="0.85">'
            '<circle cx="58" cy="30" r="1.8"/><circle cx="104" cy="52" r="1.3"/>'
            '<circle cx="150" cy="24" r="1.6"/><circle cx="232" cy="38" r="1.3"/>'
            '<circle cx="296" cy="20" r="1.7"/><circle cx="372" cy="44" r="1.2"/>'
            '<circle cx="430" cy="26" r="1.6"/><circle cx="498" cy="56" r="1.3"/>'
            '<circle cx="556" cy="32" r="1.8"/><circle cx="604" cy="62" r="1.3"/>'
            "</g>"
        )
        moon = (
            '<g transform="translate(544 52)">'
            '<circle r="24" fill="' + orb + '" opacity="' + orb_op + '"/>'
            '<circle r="20" cx="10" cy="-6" fill="rgba(16, 22, 44, 0.92)"/>'
            '<circle r="3" cx="-8" cy="6" fill="rgba(120, 130, 170, 0.35)"/>'
            '<circle r="2" cx="-3" cy="-8" fill="rgba(120, 130, 170, 0.30)"/>'
            "</g>"
        )
    else:
        sky_a, sky_b = "rgba(148, 212, 255, 0.52)", "rgba(148, 212, 255, 0.06)"
        orb, orb_op = "#ffedb0", "0.90"
        sea_back, sea_front = "rgba(118, 208, 245, 0.46)", "rgba(62, 166, 224, 0.58)"
        sand = "rgba(238, 214, 160, 0.62)"
        stars = (
            '<g fill="#ffffff" opacity="0.75">'
            '<path d="M56 34l3 8 8 3-8 3-3 8-3-8-8-3 8-3z"/>'
            '<path d="M470 26l2.4 6.4 6.4 2.4-6.4 2.4-2.4 6.4-2.4-6.4-6.4-2.4 6.4-2.4z"/>'
            '<path d="M596 52l2 5.4 5.4 2-5.4 2-2 5.4-2-5.4-5.4-2 5.4-2z"/>'
            "</g>"
        )
        moon = (
            '<g transform="translate(544 52)">'
            '<circle r="30" fill="rgba(255, 236, 168, 0.22)"/>'
            '<circle r="20" fill="' + orb + '" opacity="' + orb_op + '"/>'
            '<g stroke="' + orb + '" stroke-width="4" stroke-linecap="round" opacity="0.85">'
            '<path d="M0 -34v-9"/><path d="M0 34v9"/><path d="M-34 0h-9"/><path d="M34 0h9"/>'
            '<path d="M-24 -24l-6 -6"/><path d="M24 -24l6 -6"/>'
            '<path d="M-24 24l-6 6"/><path d="M24 24l6 6"/>'
            "</g></g>"
        )

    badge = ""
    if anonymous:
        badge = (
            '<div class="mgart-badge"><svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M3 12c3-5 6-7 9-7s6 2 9 7c-3 5-6 7-9 7s-6-2-9-7z" fill="none"'
            ' stroke="#eaf6ff" stroke-width="2"/>'
            '<circle cx="12" cy="12" r="3.2" fill="#eaf6ff"/>'
            '<path d="M4 20L20 4" stroke="#eaf6ff" stroke-width="2"/></svg>匿名瓶</div>'
        )

    svg = (
        '<svg viewBox="0 0 640 190" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
        "<defs>"
        '<linearGradient id="mgSky" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="' + sky_a + '"/>'
        '<stop offset="1" stop-color="' + sky_b + '"/></linearGradient>'
        '<linearGradient id="mgGlass" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="rgba(226, 248, 255, 0.60)"/>'
        '<stop offset="0.34" stop-color="rgba(150, 216, 246, 0.34)"/>'
        '<stop offset="1" stop-color="rgba(58, 138, 190, 0.48)"/></linearGradient>'
        "</defs>"
        '<rect width="640" height="190" fill="url(#mgSky)"/>'
        + stars
        + moon
        + '<path class="mgart-wave" d="M0 128c62-18 108 12 168 4s104-24 168-10 112 24 172 8'
        ' 132-20 132-20v80H0z" fill="' + sea_back + '"/>'
        + (
            '<g class="mgart-glass" transform="translate(322 104) rotate(-14)">'
            '<ellipse cx="0" cy="86" rx="62" ry="9" fill="rgba(255, 255, 255, 0.16)"/>'
            '<path d="M-15 -104h30v20c0 10 27 17 27 47v50a23 23 0 0 1-23 23h-38a23 23 0 0 1-23-23'
            'v-50c0-30 27-37 27-47z" fill="url(#mgGlass)" stroke="rgba(232, 250, 255, 0.70)"'
            ' stroke-width="2.4"/>'
            '<rect x="-19" y="-118" width="38" height="18" rx="4" fill="#b07b42"/>'
            '<rect x="-19" y="-118" width="38" height="5" rx="2" fill="#d09a5d"/>'
            '<rect x="-12" y="-108" width="24" height="3" rx="1.5" fill="rgba(90, 58, 24, 0.55)"/>'
            '<path d="M-22 -30v74" stroke="rgba(255, 255, 255, 0.55)" stroke-width="5"'
            ' stroke-linecap="round" opacity="0.75"/>'
            '<path d="M22 -22v62" stroke="rgba(255, 255, 255, 0.28)" stroke-width="3"'
            ' stroke-linecap="round"/>'
            '<polygon points="-34,-40 34,-58 34,-46 -34,-28" fill="rgba(255, 255, 255, 0.14)"/>'
            '<g transform="rotate(8)">'
            '<rect x="-24" y="-16" width="48" height="46" rx="4" fill="#f6e9c8"/>'
            '<rect x="-24" y="-16" width="48" height="46" rx="4" fill="none"'
            ' stroke="rgba(150, 118, 66, 0.45)" stroke-width="1.4"/>'
            '<g stroke="rgba(150, 118, 66, 0.45)" stroke-width="2" stroke-linecap="round">'
            '<path d="M-16 -4h32"/><path d="M-16 6h32"/><path d="M-16 16h22"/>'
            "</g></g></g>"
        )
        + '<path class="mgart-wave" d="M0 156c56-16 104 10 160 2s110-20 172-6 108 20 168 6'
        ' 140-18 140-18v52H0z" fill="' + sea_front + '"/>'
        '<path class="mgart-beach" d="M0 176c70-12 118 8 186 2s126-14 190-4 142 10 264-4v22H0z"'
        ' fill="' + sand + '"/>'
        '<g fill="rgba(120, 96, 56, 0.35)">'
        '<circle cx="72" cy="184" r="2"/><circle cx="146" cy="180" r="1.6"/>'
        '<circle cx="238" cy="186" r="2.2"/><circle cx="332" cy="181" r="1.6"/>'
        '<circle cx="420" cy="186" r="2"/><circle cx="512" cy="182" r="1.7"/>'
        '<circle cx="588" cy="186" r="2.1"/>'
        "</g>"
        '<g fill="none" stroke="rgba(255, 255, 255, 0.45)" stroke-width="2.4"'
        ' stroke-linecap="round">'
        '<path d="M60 142c14-10 26-10 40 0"/><path d="M470 138c14-10 26-10 40 0"/>'
        "</g>"
        "</svg>"
    )
    return '<div class="mgart-sea">' + svg + badge + "</div>" + _style(BOTTLE_CSS)

def bottle_avatar(avatar_html: str, *, anonymous: bool, label: str) -> str:
    """头像舱窗 + 署名（label 是用户可控文本，这里必须 escape）。"""
    safe = html_module.escape(str(label or ""), quote=True)
    cap = "匿名瓶" if anonymous else "瓶主"
    return (
        '<div class="mgart-who">'
        '<div class="mgart-port">' + str(avatar_html or "") + "</div>"
        '<div class="mgart-who-text">'
        '<span class="mgart-who-cap">' + cap + "</span>"
        '<span class="mgart-who-name">' + safe + "</span>"
        "</div></div>"
        + _style(BOTTLE_CSS)
    )

def bottle_note(content_html: str) -> str:
    """正文纸条：外层纸质感由本模块生成，content_html 是已净化的 Markdown 片段。"""
    return (
        '<div class="mgart-note"><div class="mg-md">'
        + str(content_html or "")
        + '</div><div class="mgart-grain"></div></div>'
        + _style(BOTTLE_CSS)
    )
