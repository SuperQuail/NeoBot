"""Validated weekly speaking windows (ISO weekdays 1–7)."""

import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

WEEK = 7 * 1440


def minute(value: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("时间必须为 HH:MM")
    h, m = map(int, value.split(":"))
    return h * 60 + m


class Window(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekdays: list[int]
    start: str
    end: str
    next_day: bool = False

    @model_validator(mode="after")
    def valid(self):
        if (
            not self.weekdays
            or len(set(self.weekdays)) != len(self.weekdays)
            or any(d < 1 or d > 7 for d in self.weekdays)
        ):
            raise ValueError("星期使用不重复的 1–7")
        duration = minute(self.end) - minute(self.start) + (1440 if self.next_day else 0)
        if not 0 < duration < 1440:
            raise ValueError("时段须大于零且小于24小时；跨夜须指定次日")
        return self


def intervals(windows: list[Window]) -> list[tuple[int, int]]:
    result = []
    for w in windows:
        for day in w.weekdays:
            start = (day - 1) * 1440 + minute(w.start)
            end = (day - 1) * 1440 + minute(w.end) + (1440 if w.next_day else 0)
            result.append((start, min(end, WEEK)))
            if end > WEEK:
                result.append((0, end - WEEK))
    return sorted(result)


def validate_windows(windows):
    spans = intervals(windows)
    if any(right[0] < left[1] for left, right in zip(spans, spans[1:])):
        raise ValueError("时段重叠（包含前日跨夜）")
    return windows


class Override(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["group", "private"]
    id: str
    windows: list[Window] = []
    _windows = field_validator("windows")(validate_windows)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value):
        if not value.strip():
            raise ValueError("会话ID不能为空")
        return value


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "Asia/Shanghai"
    windows: list[Window] = []
    overrides: list[Override] = []
    _windows = field_validator("windows")(validate_windows)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("未知时区") from exc
        return value

    @field_validator("overrides")
    @classmethod
    def unique(cls, value):
        keys = [(o.kind, o.id) for o in value]
        if len(set(keys)) != len(keys):
            raise ValueError("同一会话不能重复覆盖")
        return value
