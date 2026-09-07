"""睡眠服务单元测试:时长解析 / 睡眠状态机 / 唤醒提示词。"""

from __future__ import annotations

import asyncio

import pytest

import neobot_app.runtime.sleep_service as sleep_module
from neobot_app.runtime.sleep_service import (
    DEFAULT_WAKE_PROMPT,
    MAX_SLEEP_SECONDS,
    SleepService,
    format_sleep_duration,
    parse_sleep_duration,
)


# ── 时长解析 ──


def test_parse_duration_units() -> None:
    assert parse_sleep_duration("90s") == (90.0, None)
    assert parse_sleep_duration("2m") == (120.0, None)
    assert parse_sleep_duration("2h") == (7200.0, None)
    assert parse_sleep_duration("1.5h") == (5400.0, None)
    assert parse_sleep_duration("30") == (1800.0, None)  # 裸数字按分钟
    assert parse_sleep_duration("12h") == (43200.0, None)  # 上限恰好允许
    assert parse_sleep_duration(" 2H ") == (7200.0, None)  # 大小写与空白


def test_parse_duration_invalid() -> None:
    _, error = parse_sleep_duration("abc")
    assert error is not None
    _, error = parse_sleep_duration("")
    assert error is not None
    _, error = parse_sleep_duration(None)
    assert error is not None
    _, error = parse_sleep_duration("0")
    assert error is not None
    _, error = parse_sleep_duration("-5m")
    assert error is not None
    _, error = parse_sleep_duration("13h")
    assert error is not None and "12" in error
    _, error = parse_sleep_duration("721m")  # 12 小时 1 分,超限
    assert error is not None and "12" in error


def test_format_duration() -> None:
    assert format_sleep_duration(1800) == "30 分钟"
    assert format_sleep_duration(3600) == "1 小时"
    assert format_sleep_duration(5400) == "1 小时 30 分钟"


# ── 状态机 ──


def test_sleep_and_wake() -> None:
    service = SleepService()
    assert not service.is_sleeping()
    assert service.remaining_seconds() == 0
    assert service.wake_up_at() is None

    ok, message = service.sleep(3600)
    assert ok
    assert "睡觉" in message
    assert "1 小时" in message
    assert service.is_sleeping()
    assert 3595 <= service.remaining_seconds() <= 3600
    assert service.wake_up_at() is not None
    assert service.wake_up_time_text() != ""

    assert service.wake() is True
    assert not service.is_sleeping()
    assert service.wake() is False  # 已醒来,再次唤醒返回 False


def test_sleep_caps_at_max() -> None:
    service = SleepService()
    ok, message = service.sleep(MAX_SLEEP_SECONDS + 1)
    assert not ok
    assert "12" in message
    assert not service.is_sleeping()


def test_sleep_rejects_zero_or_negative() -> None:
    service = SleepService()
    ok, _ = service.sleep(0)
    assert not ok
    ok, _ = service.sleep(-60)
    assert not ok
    assert not service.is_sleeping()


def test_sleep_resets_when_called_again() -> None:
    service = SleepService()
    service.sleep(3600)
    service.sleep(120)
    assert service.is_sleeping()
    assert service.remaining_seconds() <= 120


def test_sleep_expires_by_time(monkeypatch) -> None:
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    service = SleepService()
    service.sleep(60)
    assert service.is_sleeping()
    assert service.remaining_seconds() == 60

    fake["now"] = 1060.0
    assert not service.is_sleeping()  # 时间到自动醒来
    assert service.remaining_seconds() == 0
    assert service.wake_up_at() is None


@pytest.mark.parametrize("wall_shift", [7200.0, -7200.0])
def test_sleep_duration_ignores_wall_clock_adjustment(monkeypatch, wall_shift) -> None:
    """系统时间前跳或回拨时，睡眠仍按实际经过时长到期。"""
    clock = {"wall": 10000.0, "mono": 100.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: clock["wall"])
    monkeypatch.setattr(
        sleep_module, "monotonic_seconds", lambda: clock["mono"]
    )
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)
    service.sleep(3600)
    assert service.wake_up_at() == 13600.0

    clock["wall"] += wall_shift
    clock["mono"] += 300

    assert service.is_sleeping()
    assert service.remaining_seconds() == 3300
    assert service._sleep_elapsed_text() == "5 分钟"
    clock["mono"] = 3699.0
    assert service.is_sleeping()
    assert service.remaining_seconds() == 1
    clock["mono"] = 3700.0
    assert not service.is_sleeping()
    assert service.remaining_seconds() == 0
    assert service.wake_up_at() is None
    assert not service.is_sleeping()
    expiry = [record for record in recorder.records if "Bot 睡眠到期" in record[0]]
    assert len(expiry) == 1
    assert expiry[0][1]["elapsed_text"] == "1 小时"


def test_sleep_resets_monotonic_deadline_and_manual_wake(monkeypatch) -> None:
    """重复 sleep 重新计时，主动唤醒后新睡眠不沿用旧截止时间。"""
    clock = {"wall": 10000.0, "mono": 100.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: clock["wall"])
    monkeypatch.setattr(
        sleep_module, "monotonic_seconds", lambda: clock["mono"]
    )
    service = SleepService()
    service.sleep(3600)

    clock["mono"] = 400.0
    service.sleep(120)
    clock["mono"] = 519.0

    assert service.remaining_seconds() == 1
    assert service.wake(reason="awake_command")
    assert service.wake_up_at() is None
    assert service.remaining_seconds() == 0
    service.sleep(60)
    clock["mono"] = 579.0
    assert not service.is_sleeping()


# ── 唤醒提示词(自定义提示词系统) ──


def test_wake_prompt_default() -> None:
    service = SleepService()
    assert service.wake_prompt() == DEFAULT_WAKE_PROMPT


def test_wake_prompt_custom_from_store() -> None:
    import shutil
    import uuid
    from pathlib import Path

    from neobot_app.prompt.store import PromptStore

    # 使用工作区内的临时目录(沙箱环境不保证系统临时目录可写)
    data_dir = Path("st_" + uuid.uuid4().hex[:8])
    try:
        custom_dir = data_dir / "prompts" / "custom"
        custom_dir.mkdir(parents=True)
        (custom_dir / "prompts.toml").write_text(
            '[wake_up]\ntemplate = "自定义唤醒提示词"\n',
            encoding="utf-8",
        )
        store = PromptStore(data_dir)
        service = SleepService(prompt_store=store)
        assert service.wake_prompt() == "自定义唤醒提示词"
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)

# ── 睡眠结束日志(控制台定位用) ──


class _LogRecorder:
    """收集 logger.info 调用的假 logger。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def info(self, message: str, **kwargs) -> None:
        self.records.append((message, dict(kwargs)))

    def warning(self, message: str, **kwargs) -> None:
        self.records.append((message, dict(kwargs)))

    def debug(self, message: str, **kwargs) -> None:
        pass

    def error(self, message: str, **kwargs) -> None:
        pass


def test_wake_logs_reason_and_elapsed(monkeypatch) -> None:
    """wake() 记录唤醒来源与已持续时长,便于定位提前结束原因。"""
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)

    service.sleep(3600)
    fake["now"] = 1300.0
    assert service.wake(reason="awake_command") is True

    messages = [message for message, _ in recorder.records]
    assert any("Bot 开始睡眠" in message for message in messages)
    assert any("Bot 被唤醒" in message for message in messages)
    wake_record = next(
        record for record in recorder.records if "Bot 被唤醒" in record[0]
    )
    assert wake_record[1]["reason"] == "awake_command"
    assert wake_record[1]["elapsed_text"] == "5 分钟"


def test_sleep_expiry_logs_awake(monkeypatch) -> None:
    """睡眠到期自动醒来时打印日志(时间到与被动唤醒可区分)。"""
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)

    service.sleep(60)
    assert service.is_sleeping()
    fake["now"] = 1060.0
    assert not service.is_sleeping()

    messages = [message for message, _ in recorder.records]
    assert any("Bot 睡眠到期,自动醒来" in message for message in messages)
    expiry_record = next(
        record
        for record in recorder.records
        if "Bot 睡眠到期,自动醒来" in record[0]
    )
    assert expiry_record[1]["elapsed_text"] == "1 分钟"


def test_wake_without_reason_uses_unknown(monkeypatch) -> None:
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)
    service.sleep(60)
    service.wake()
    wake_record = next(
        record for record in recorder.records if "Bot 被唤醒" in record[0]
    )
    assert wake_record[1]["reason"] == "unknown"

def test_log_remaining_prints_during_sleep(monkeypatch) -> None:
    """睡眠中每分钟播报剩余时间(带可读文本与秒数)。"""
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)

    service.sleep(3600)
    service._log_remaining()

    records = [
        record for record in recorder.records if "睡眠中,剩余睡眠时间" in record[0]
    ]
    assert len(records) == 1
    assert "剩余睡眠时间1 小时" in records[0][0]
    assert records[0][1]["remaining_seconds"] == 3600


def test_log_remaining_silent_when_awake(monkeypatch) -> None:
    """未睡眠时不打印剩余时间播报。"""
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)

    service._log_remaining()

    assert not any(
        "睡眠中,剩余睡眠时间" in record[0] for record in recorder.records
    )


async def test_ticker_loop_polls_remaining(monkeypatch) -> None:
    """ticker 循环按间隔播报剩余时间(睡眠中打印,醒来后停止)。"""
    fake = {"now": 1000.0}
    monkeypatch.setattr(sleep_module, "epoch_seconds", lambda: fake["now"])
    monkeypatch.setattr(sleep_module, "monotonic_seconds", lambda: fake["now"])
    recorder = _LogRecorder()
    service = SleepService(logger=recorder)
    service.sleep(120)

    task = asyncio.create_task(service._ticker_loop(interval_seconds=0.01))
    await asyncio.sleep(0.045)  # 约 4 轮播报
    logs_during_sleep = [
        record for record in recorder.records if "睡眠中,剩余睡眠时间" in record[0]
    ]
    assert len(logs_during_sleep) >= 2

    service.wake()
    await asyncio.sleep(0.04)  # 醒来后不再打印
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    logs_after_wake = [
        record for record in recorder.records if "睡眠中,剩余睡眠时间" in record[0]
    ]
    assert len(logs_after_wake) == len(logs_during_sleep)


