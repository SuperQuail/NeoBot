"""neobot_app.utils.time 时区/UTC 转换与日期工具测试。"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

import neobot_app.time_context as time_context
from neobot_app.utils import time as time_utils


def test_to_utc_treats_naive_datetime_as_local() -> None:
    """Arrange: 无时区 datetime 按本地时区(+8)解释；Act: 转 UTC；Assert: 时刻不变。"""
    naive = datetime(2024, 1, 1, 0, 0, 0)

    result = time_utils.to_utc(naive)

    assert result.tzinfo == timezone.utc
    assert result == datetime(2023, 12, 31, 16, 0, 0, tzinfo=timezone.utc)


def test_to_utc_converts_aware_local_datetime() -> None:
    """Arrange: 带本地时区(+8)的 aware datetime；Act: 转 UTC；Assert: 正确减 8 小时。"""
    local_aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=time_context.LOCAL_TIMEZONE)

    result = time_utils.to_utc(local_aware)

    assert result == datetime(2024, 6, 1, 4, 0, 0, tzinfo=timezone.utc)


def test_to_local_roundtrip_preserves_instant() -> None:
    """Arrange: 任意 aware 时刻；Act: to_utc 后 to_local 往返；Assert: 时刻（timestamp）不变。"""
    utc = datetime(2024, 3, 15, 8, 30, 0, tzinfo=timezone.utc)

    roundtrip = time_utils.to_local(time_utils.to_utc(utc))

    assert roundtrip.timestamp() == pytest.approx(utc.timestamp())
    assert roundtrip.tzinfo == time_context.LOCAL_TIMEZONE


def test_to_local_keeps_naive_datetime_as_local() -> None:
    """Arrange: 无时区 datetime；Act: to_local；Assert: 仅标记为本地时区，不偏移。"""
    naive = datetime(2024, 1, 1, 10, 30, 0)

    result = time_utils.to_local(naive)

    assert result.tzinfo == time_context.LOCAL_TIMEZONE
    assert result.hour == 10 and result.minute == 30


def test_today_local_returns_fixed_timezone_date(monkeypatch) -> None:
    """Arrange: 固定 now_local 为 2024-01-01 23:30 (+8)；Act: today_local；Assert: 返回对应日期。"""
    fixed = datetime(2024, 1, 1, 23, 30, 0, tzinfo=time_context.LOCAL_TIMEZONE)
    monkeypatch.setattr(time_context, "now_local", lambda: fixed)

    result = time_utils.today_local()

    assert result == date(2024, 1, 1)


def test_today_local_matches_now_local_date() -> None:
    """Arrange: 直接调用 today_local 与 now_local；Act: 比较日期；Assert: 两者一致。"""
    result = time_utils.today_local()

    assert isinstance(result, date)
    assert result == time_utils.now_local().date()


def test_filename_timestamp_matches_format(monkeypatch) -> None:
    """Arrange: 固定本地时间；Act: filename_timestamp；Assert: 格式为 YYYYMMDD_HHMMSS。"""
    fixed = datetime(2024, 12, 31, 9, 5, 7, tzinfo=time_context.LOCAL_TIMEZONE)
    monkeypatch.setattr(time_context, "now_local", lambda: fixed)

    result = time_utils.filename_timestamp()

    assert result == "20241231_090507"
    assert len(result) == 15


def test_epoch_seconds_int_matches_epoch_seconds() -> None:
    """Arrange: 无参数；Act: 同时取 epoch_seconds 与 epoch_seconds_int；Assert: 类型与近似值。"""
    result = time_utils.epoch_seconds_int()

    assert isinstance(result, int)
    assert abs(result - time_utils.epoch_seconds()) < 1


def test_combine_local_builds_aware_datetime() -> None:
    """Arrange: 日期与时分秒；Act: combine_local；Assert: 结果带本地时区且字段正确。"""
    day = date(2024, 7, 1)
    clock = time(13, 45, 30)

    result = time_utils.combine_local(day, clock)

    assert result.tzinfo == time_context.LOCAL_TIMEZONE
    assert result == datetime(2024, 7, 1, 13, 45, 30, tzinfo=time_context.LOCAL_TIMEZONE)


def test_now_utc_is_utc_aware() -> None:
    """Arrange: 无参数；Act: now_utc；Assert: 返回 UTC 时区的 aware datetime。"""
    result = time_utils.now_utc()

    assert result.tzinfo == timezone.utc
    assert isinstance(result, datetime)


def test_lunar_date_text_returns_text() -> None:
    """Arrange: 指定公历日期 2024-02-10（甲辰年正月初一）；Act: lunar_date_text；Assert: 返回农历正月初一。"""
    result = time_utils.lunar_date_text(date(2024, 2, 10))

    assert isinstance(result, str)
    assert result == "正月初一"


def test_get_current_time_and_lunar_date_contains_time() -> None:
    """Arrange: 无参数；Act: get_current_time_and_lunar_date；Assert: 包含时间与农历前缀。"""
    result = time_utils.get_current_time_and_lunar_date()

    assert "现在的时间是" in result
    assert "农历日期是" in result
