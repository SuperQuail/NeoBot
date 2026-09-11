"""沙箱维护调度：按持久化的运行记录决定是否执行，重启不再无条件重跑。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from neobot_app.bootstrap import (
    DEFAULT_MAINTENANCE_INTERVAL_SECONDS,
    plan_maintenance_run,
)

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
INTERVAL = 43200  # 12 小时


def _plan(last_success, last_status, *, interval: int = INTERVAL):
    return plan_maintenance_run(
        last_success=last_success,
        last_status=last_status,
        interval_seconds=interval,
        now=NOW,
    )


def test_never_ran_triggers_maintenance():
    plan = _plan(None, None)
    assert plan.due is True
    assert plan.wait_seconds == 0


def test_recent_success_is_skipped_until_interval():
    """重启后未到期必须跳过——这是「无意义沙箱维护」的直接修复点。"""
    last = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    plan = _plan(last, "success")
    assert plan.due is False
    assert plan.wait_seconds == pytest.approx(INTERVAL - 300, abs=1)
    assert "距上次成功维护" in plan.reason


def test_success_past_interval_runs():
    last = (NOW - timedelta(seconds=INTERVAL + 1)).replace(tzinfo=None)
    assert _plan(last, "success").due is True


def test_exactly_at_interval_runs():
    last = (NOW - timedelta(seconds=INTERVAL)).replace(tzinfo=None)
    assert _plan(last, "success").due is True


@pytest.mark.parametrize("status", ["failed", "running"])
def test_unfinished_previous_attempt_runs_immediately(status):
    """上次失败，或上次是 running（进程被中断）时立即补跑一次。"""
    last = (NOW - timedelta(minutes=1)).replace(tzinfo=None)
    plan = _plan(last, status)
    assert plan.due is True
    assert plan.wait_seconds == 0


def test_skipped_status_does_not_force_retry():
    """跳过记录不算失败，仍按上次成功时间判断。"""
    last = (NOW - timedelta(hours=1)).replace(tzinfo=None)
    plan = _plan(last, "skipped")
    assert plan.due is False


def test_naive_timestamps_are_read_as_utc():
    """时间列是无时区 UTC；按本地时区解读会让 8 小时窗口错位。"""
    last_utc_naive = (NOW - timedelta(hours=1)).replace(tzinfo=None)
    aware_local = last_utc_naive.replace(tzinfo=timezone(timedelta(hours=8)))
    assert _plan(last_utc_naive, "success").due is False
    # 同一时刻以 aware 形式传入也必须得到同一结论
    assert _plan(aware_local, "success").due is False


def test_default_interval_is_three_hours():
    assert DEFAULT_MAINTENANCE_INTERVAL_SECONDS == 10800
