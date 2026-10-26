"""签到卡片美术：日历页与印章。"""

from __future__ import annotations

import html as html_module

from .art_common import _style
from .art_fortune import WEEKDAYS


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
