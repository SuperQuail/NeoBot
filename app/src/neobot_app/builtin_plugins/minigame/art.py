"""四个玩法卡片的专属美术片段（全部由插件自己用 SVG 画出来）。

安全边界：片段只由**模块常量 + 程序产出的数字**拼成，不含任何用户输入；
用户文本一律先经渲染器的 escape → Markdown → URL 清洗，才进入卡片正文。
片段里没有外链、没有 script、没有事件处理器，因此可以安全地用 inject_slot 注入。

每个片段自带一段内联 style（类名统一前缀 mg-*），颜色尽量引用主题变量
（--accent / --panel-bg / --panel-border），这样同一份美术在「玩法艺术主题」
与「minecraft 主题」下都协调。
"""

from __future__ import annotations

import html as html_module

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


def _style(css: str) -> str:
    return "<style>" + css + "</style>" if css else ""


def safe_level_label(label: str) -> str:
    """只允许已知档位文字进入 SVG（防注入：任何其它值一律不画）。"""
    text = str(label or "").strip()
    return text if text in FORTUNE_LABELS else ""


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


# ----------------------------------------------------------------------
# 成语接龙：卷轴 + 毛笔 + 印章 + 进度节点
# ----------------------------------------------------------------------

CHENGYU_CSS = """\
.mgart-scroll { position: relative; margin: 0 0 12px; }
.mgart-scroll svg { display: block; width: 100%; height: auto; }
.mgart-progress { position: relative; margin: 0 0 14px; padding: 10px 12px 6px; border-radius: 6px;
  border: 1px solid var(--panel-border); background: var(--panel-bg); }
.mgart-progress svg { display: block; width: 100%; height: auto; }
.mgart-progress-cap { display: flex; align-items: baseline; justify-content: space-between;
  gap: 10px; margin: 0 2px 4px; font-size: 12.5px; letter-spacing: 0.08em; color: var(--card-muted); }
.mgart-progress-now { font-size: 15px; font-weight: 700; color: var(--accent); letter-spacing: 0.06em; }
"""


def chengyu_scroll(*, status: str) -> str:
    """卷轴头：上下木轴 + 宣纸 + 毛笔笔触 + 朱砂印（status 是程序常量文字）。"""
    caption = str(status or "").strip()
    svg = (
        '<svg viewBox="0 0 640 118" preserveAspectRatio="none" aria-hidden="true">'
        "<defs>"
        '<linearGradient id="mgRod" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#9a6738"/><stop offset="0.45" stop-color="#6b4526"/>'
        '<stop offset="1" stop-color="#3f2817"/></linearGradient>'
        '<linearGradient id="mgPaper" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="rgba(255, 253, 245, 0.94)"/>'
        '<stop offset="1" stop-color="rgba(246, 236, 214, 0.90)"/></linearGradient>'
        "</defs>"
        '<rect x="14" y="4" width="612" height="14" rx="7" fill="url(#mgRod)"/>'
        '<rect x="14" y="100" width="612" height="14" rx="7" fill="url(#mgRod)"/>'
        '<circle cx="18" cy="11" r="10" fill="#a9784a"/><circle cx="18" cy="11" r="4"'
        ' fill="#e0bc8c"/>'
        '<circle cx="622" cy="11" r="10" fill="#a9784a"/><circle cx="622" cy="11" r="4"'
        ' fill="#e0bc8c"/>'
        '<circle cx="18" cy="107" r="10" fill="#a9784a"/><circle cx="18" cy="107" r="4"'
        ' fill="#e0bc8c"/>'
        '<circle cx="622" cy="107" r="10" fill="#a9784a"/><circle cx="622" cy="107" r="4"'
        ' fill="#e0bc8c"/>'
        '<rect x="20" y="16" width="600" height="86" fill="url(#mgPaper)"/>'
        '<g fill="rgba(58, 44, 28, 0.16)">'
        '<path d="M58 74c40-30 78 10 118-10s72-30 112-12 70 26 112 8 58-16 100-8v10'
        'c-42-8-62 4-100 12s-70 6-112-8-72-6-112 12-78-8-118 12z"/>'
        "</g>"
        '<g fill="rgba(58, 44, 28, 0.10)">'
        '<path d="M64 44c34-18 66 6 100-8s62-22 96-8 60 20 96 6 52-12 88-6v8'
        'c-36-6-52 0-88 6s-60 4-96-6-62-4-96 8-66-4-100 8z"/>'
        "</g>"
        '<g class="mgart-brush" transform="translate(48 30) rotate(-24)">'
        '<rect x="-6" y="-46" width="12" height="62" rx="6" fill="#4a3524"/>'
        '<rect x="-7" y="16" width="14" height="10" rx="2" fill="#d8ab5c"/>'
        '<path d="M-7 26c0 16 4 26 7 32 3-6 7-16 7-32z" fill="#2b2118"/>'
        '<path d="M-2 26c0 14 1 22 2 26 1-4 2-12 2-26z" fill="#5a4632"/>'
        "</g>"
        '<g class="mgart-seal" transform="translate(556 74) rotate(-6)">'
        '<rect x="-24" y="-24" width="48" height="48" rx="5" fill="rgba(168, 53, 42, 0.90)"'
        ' stroke="#8d2417" stroke-width="2.5"/>'
        '<g fill="#fff4ec" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif"'
        ' font-size="26" text-anchor="middle">'
        '<text x="0" y="10">\u9f99</text>'
        "</g></g>"
        '<rect x="20" y="16" width="600" height="86" fill="none"'
        ' stroke="rgba(150, 118, 66, 0.45)" stroke-width="2"/>'
        + (
            '<g fill="#8d2417" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif"'
            ' font-size="22" text-anchor="middle" letter-spacing="4">'
            '<text x="320" y="72">' + html_module.escape(caption) + "</text></g>"
            if caption
            else ""
        )
        + "</svg>"
    )
    return '<div class="mgart-scroll">' + svg + "</div>" + _style(CHENGYU_CSS)


def chengyu_progress(*, steps: int, target: int, max_steps: int) -> str:
    """进度节点链：已接的节点填朱砂，当前节点加粗环；纯数字，无用户输入。"""
    count = max(1, min(int(target or 1), 60))
    done = max(0, min(int(steps or 0), count))
    left = 30.0
    right = 610.0
    span = right - left
    radius = 9.0 if count <= 12 else (6.0 if count <= 24 else 4.0)
    nodes: list[str] = []
    for index in range(1, count + 1):
        x = left if count == 1 else left + span * (index - 1) / (count - 1)
        if index <= done:
            nodes.append(
                '<circle cx="' + str(round(x, 1)) + '" cy="30" r="' + str(radius)
                + '" fill="#a8352a"/>'
                '<circle cx="' + str(round(x, 1)) + '" cy="30" r="' + str(round(radius * 0.4, 1))
                + '" fill="#fff4ec"/>'
            )
        else:
            nodes.append(
                '<circle cx="' + str(round(x, 1)) + '" cy="30" r="' + str(radius)
                + '" fill="rgba(255, 255, 255, 0.55)" stroke="rgba(110, 86, 48, 0.55)"'
                ' stroke-width="2"/>'
            )
    ring = ""
    if 0 < done <= count:
        x = left if count == 1 else left + span * (done - 1) / (count - 1)
        ring = (
            '<circle cx="' + str(round(x, 1)) + '" cy="30" r="' + str(radius + 6)
            + '" fill="none" stroke="rgba(168, 53, 42, 0.45)" stroke-width="2.4"'
            ' stroke-dasharray="4 4"/>'
        )
    filled = 0.0 if count == 1 else span * done / count
    svg = (
        '<svg viewBox="0 0 640 60" preserveAspectRatio="none" aria-hidden="true">'
        '<rect x="30" y="26" width="580" height="8" rx="4" fill="rgba(110, 86, 48, 0.18)"/>'
        '<rect x="30" y="26" width="' + str(round(filled, 1)) + '" height="8" rx="4"'
        ' fill="rgba(168, 53, 42, 0.72)"/>'
        + ring
        + "".join(nodes)
        + "</svg>"
    )
    cap = (
        '<div class="mgart-progress-cap">'
        '<span>接龙进度 · 目标 ' + str(count) + " 条</span>"
        '<span class="mgart-progress-now">第 ' + str(done) + "/" + str(count) + " 条</span>"
        '<span>单局最多 ' + str(int(max_steps or 0)) + " 步</span>"
        "</div>"
    )
    return '<div class="mgart-progress">' + cap + svg + "</div>" + _style(CHENGYU_CSS)


# ----------------------------------------------------------------------
# 签到：日历页 + 打卡印章 + 连续天数点阵
# ----------------------------------------------------------------------

CHECKIN_CSS = """\
.mgart-cal { position: relative; display: flex; align-items: stretch; gap: 14px; margin: 0 0 14px; }
.mgart-cal-page { position: relative; flex: 0 0 132px; border-radius: 10px; overflow: hidden;
  background: #ffffff; border: 1px solid rgba(150, 134, 112, 0.28);
  box-shadow: 0 8px 18px rgba(70, 58, 38, 0.14); }
.mgart-cal-page svg { display: block; width: 100%; height: auto; }
.mgart-stamp { position: relative; flex: 1 1 auto; display: flex; flex-direction: column;
  justify-content: center; gap: 8px; padding: 12px 14px; border-radius: 10px;
  border: 1px dashed rgba(216, 67, 58, 0.45); background: rgba(216, 67, 58, 0.06); }
.mgart-stamp-mark { display: flex; align-items: center; gap: 10px; }
.mgart-stamp-mark svg { width: 62px; height: 62px; flex: 0 0 auto; }
.mgart-stamp-text { display: flex; flex-direction: column; gap: 2px; }
.mgart-stamp-title { font-size: 17px; font-weight: 800; letter-spacing: 0.14em; color: #c23a32; }
.mgart-stamp-sub { font-size: 12px; letter-spacing: 0.08em; color: var(--card-muted); }
.mgart-streak { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; padding: 8px 12px;
  border-radius: 10px; border: 1px solid var(--panel-border); background: var(--panel-bg); }
.mgart-streak-cap { font-size: 12px; letter-spacing: 0.10em; color: var(--card-muted); white-space: nowrap; }
.mgart-streak-dots { display: flex; flex-wrap: wrap; gap: 6px; }
.mgart-streak-dot { width: 12px; height: 12px; border-radius: 50%;
  background: rgba(150, 134, 112, 0.24); box-shadow: inset 0 0 0 1px rgba(150, 134, 112, 0.35); }
.mgart-streak-dot.is-on { background: #d8433a; box-shadow: inset 0 0 0 1px rgba(148, 34, 26, 0.55); }
.mgart-streak-dot.is-now { outline: 2px solid rgba(216, 67, 58, 0.45); outline-offset: 2px; }
.mgart-streak-num { font-size: 15px; font-weight: 800; color: #c23a32; letter-spacing: 0.04em; }
"""


def _calendar_page(*, day: str) -> str:
    """日历页（年/月 + 大号日期 + 当月格阵）：日期与连续性都来自程序。"""
    year = month = number = ""
    weekday = ""
    text = str(day or "").strip()
    parts = text.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, number = parts[0], str(int(parts[1])), str(int(parts[2]))
        try:
            import datetime as _dt

            index = _dt.date(int(parts[0]), int(parts[1]), int(parts[2])).weekday()
            weekday = WEEKDAYS[index]
        except ValueError:
            weekday = ""
    cells: list[str] = []
    for index in range(21):
        column = index % 7
        row = index // 7
        x = 14 + column * 15
        y = 96 + row * 15
        marked = bool(number) and index == (int(number) - 1) % 21
        cells.append(
            '<rect x="' + str(x) + '" y="' + str(y) + '" width="11" height="11" rx="2" fill="'
            + ("#d8433a" if marked else "rgba(150, 134, 112, 0.20)")
            + '"/>'
        )
    marks = "".join(cells)
    svg = (
        '<svg viewBox="0 0 118 168" aria-hidden="true">'
        '<rect width="118" height="168" fill="#ffffff"/>'
        '<path d="M0 0h118v34H0z" fill="#d8433a"/>'
        '<path d="M0 34h118v3H0z" fill="rgba(148, 34, 26, 0.45)"/>'
        '<g fill="#ffffff" font-family="Microsoft YaHei, PingFang SC, sans-serif"'
        ' text-anchor="middle">'
        '<text x="59" y="23" font-size="15" letter-spacing="1">' + html_module.escape(str(year))
        + " · " + html_module.escape(str(month)) + "</text>"
        "</g>"
        '<g fill="#3b3730" font-family="Microsoft YaHei, PingFang SC, sans-serif"'
        ' text-anchor="middle">'
        '<text x="59" y="78" font-size="42" font-weight="bold">' + html_module.escape(str(number))
        + "</text>"
        "</g>"
        '<g fill="rgba(120, 108, 92, 0.75)" font-family="Microsoft YaHei, PingFang SC, sans-serif"'
        ' text-anchor="middle">'
        '<text x="59" y="92" font-size="11">星期' + html_module.escape(str(weekday)) + "</text>"
        "</g>"
        + marks
        + '<g fill="rgba(216, 67, 58, 0.45)">'
        '<rect x="14" y="76" width="90" height="2" rx="1"/>'
        "</g>"
        "</svg>"
    )
    return '<div class="mgart-cal-page">' + svg + "</div>"


def _stamp_mark(*, already: bool) -> str:
    """打卡印章：重复签到时改用灰调，避免「又盖了一次红章」的误导。"""
    chars = list("已签" if already else "签到")
    size = 22
    step = 26
    first = 36 - step * (len(chars) - 1) / 2 + size * 0.34
    texts: list[str] = []
    for index, char in enumerate(chars):
        texts.append(
            '<text x="36" y="' + str(round(first + index * step, 1)) + '">'
            + html_module.escape(char) + "</text>"
        )
    svg = (
        '<svg viewBox="0 0 72 72" aria-hidden="true">'
        '<g transform="rotate(-11 36 36)">'
        '<rect x="6" y="6" width="60" height="60" rx="9" fill="none" stroke="'
        + ("rgba(150, 134, 112, 0.65)" if already else "#c8382b")
        + '" stroke-width="4"/>'
        '<rect x="12" y="12" width="48" height="48" rx="5" fill="none" stroke="'
        + ("rgba(150, 134, 112, 0.45)" if already else "rgba(200, 56, 43, 0.75)")
        + '" stroke-width="1.6"/>'
        '<g fill="' + ("#8d8478" if already else "#c8382b")
        + '" font-family="Kaiti SC, KaiTi, STKaiti, Songti SC, serif" font-size="' + str(size)
        + '" text-anchor="middle">' + "".join(texts) + "</g></g>"
        '<circle cx="36" cy="36" r="33" fill="none" stroke="'
        + ("rgba(150, 134, 112, 0.30)" if already else "rgba(200, 56, 43, 0.35)")
        + '" stroke-width="1.5" stroke-dasharray="3 5"/>'
        "</svg>"
    )
    return svg


def checkin_art(*, day: str, streak: int, already: bool) -> str:
    """签到卡片美术：日历页 + 打卡印章 + 连续天数点阵。"""
    days = max(0, int(streak or 0))
    window = 14
    dots: list[str] = []
    filled = min(days, window)
    for index in range(window):
        classes = ["mgart-streak-dot"]
        if index < filled:
            classes.append("is-on")
        if index == filled - 1 and filled:
            classes.append("is-now")
        dots.append('<i class="' + " ".join(classes) + '"></i>')
    overflow = days - window
    note = ("（另 +" + str(overflow) + " 天）") if overflow > 0 else ""
    stamp = (
        '<div class="mgart-stamp">'
        '<div class="mgart-stamp-mark">'
        + _stamp_mark(already=already)
        + '<div class="mgart-stamp-text">'
        '<span class="mgart-stamp-title">' + ("今日已打卡" if already else "打卡成功") + "</span>"
        '<span class="mgart-stamp-sub">'
        + ("重复签到不重复加分" if already else "印章已盖，今天也算上啦")
        + "</span></div></div></div>"
    )
    calendar = '<div class="mgart-cal">' + _calendar_page(day=day) + stamp + "</div>"
    streak_bar = (
        '<div class="mgart-streak">'
        '<span class="mgart-streak-cap">连续签到</span>'
        '<span class="mgart-streak-dots">' + "".join(dots) + "</span>"
        '<span class="mgart-streak-num">' + str(days) + " 天" + note + "</span>"
        "</div>"
    )
    return calendar + streak_bar + _style(CHECKIN_CSS)


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
