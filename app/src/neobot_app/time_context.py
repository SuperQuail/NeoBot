"""Central time helpers for NeoBot application code.

Application code should use this module for wall-clock time so prompts,
scheduled tasks, debug records, and runtime expiry checks share the same
timezone and formatting assumptions.
"""

from __future__ import annotations

import time
from datetime import date, datetime, time as dtime, timedelta, timezone

from lunarcalendar import Converter, Solar
from neobot_contracts.time_context import now_utc as _contract_now_utc


LOCAL_TIMEZONE = timezone(timedelta(hours=8), "Asia/Hong_Kong")
WEEKDAY_NAMES = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


class LunarStr:
    months = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
    days = [
        "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
        "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
        "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
    ]

    @classmethod
    def from_year_month_day(cls, year: int, month: int, day: int) -> "LunarStr":
        solar = Solar(year, month, day)
        lunar = Converter.Solar2Lunar(solar)
        return cls(lunar)

    def __repr__(self) -> str:
        return f"LunarStr(year={self.year}, month={self.month}, day={self.day})"

    def __init__(self, lunar) -> None:
        self.year = lunar.year
        self.month = lunar.month
        self.day = lunar.day
        try:
            self.month_str = self.months[lunar.month - 1]
            self.day_str = self.days[lunar.day - 1]
        except IndexError as exc:
            raise ValueError("月份或日期超出有效范围！") from exc
        if lunar.isleap:
            self.month_str = "闰" + self.month_str

    def get_calendar_date_str(self) -> str:
        if self.day == 1:
            return self.month_str
        return self.day_str

    def get_date_str(self) -> str:
        return self.month_str + self.day_str


def now_utc() -> datetime:
    return _contract_now_utc()


def now_local() -> datetime:
    return datetime.now(LOCAL_TIMEZONE)


def today_local() -> date:
    return now_local().date()


def epoch_seconds() -> float:
    return time.time()


def epoch_seconds_int() -> int:
    return int(epoch_seconds())


def from_epoch_seconds(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE)


def monotonic_seconds() -> float:
    return time.monotonic()


def filename_timestamp() -> str:
    return now_local().strftime("%Y%m%d_%H%M%S")


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TIMEZONE).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def to_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TIMEZONE)
    return value.astimezone(LOCAL_TIMEZONE)


def combine_local(day: date, clock: dtime) -> datetime:
    return datetime.combine(day, clock).replace(tzinfo=LOCAL_TIMEZONE)


def lunar_date_text(day: date | None = None) -> str:
    target = day or today_local()
    lunar = Converter.Solar2Lunar(Solar.from_date(target))
    return LunarStr(lunar).get_date_str()


def get_current_time_and_lunar_date() -> str:
    current = now_local()
    current_time = current.strftime("%Y-%m-%d %H:%M:%S")
    week = WEEKDAY_NAMES[current.weekday()]
    return f"现在的时间是{current_time},{week}.农历日期是{lunar_date_text(current.date())}"
