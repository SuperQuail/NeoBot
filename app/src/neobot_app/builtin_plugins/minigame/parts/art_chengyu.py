"""成语接龙卡片美术：卷轴与进度条。"""

from __future__ import annotations

import html as html_module

from .art_common import _style


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
