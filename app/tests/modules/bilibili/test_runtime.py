"""BilibiliRuntime 测试：每日动态日记的排期、跨天、失败隔离与取消。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from neobot_app.bilibili.runtime import BilibiliRuntime

_TZ = timezone(timedelta(hours=8))


def _runtime(tmp_path, **overrides) -> BilibiliRuntime:
    values = {
        "cookie_file": str(tmp_path / "cookies.json"),
        "dynamic_diary_enabled": True,
        "dynamic_diary_time": "22:30",
        "comment_reply_enabled": False,
        "private_message_enabled": False,
        "poll_interval_seconds": 1800,
    }
    values.update(overrides)
    config = SimpleNamespace(
        bilibili=SimpleNamespace(**values),
        bot=SimpleNamespace(nick_name="", bot_data=""),
    )
    return BilibiliRuntime(
        config=config,
        provider=None,
        archive_service=None,
        uow_factory=None,
        command_service=None,
    )


def test_seconds_until_diary_handles_same_day_and_cross_day(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    now = datetime(2026, 10, 19, 22, 0, tzinfo=_TZ)
    assert runtime._seconds_until_diary(now) == 30 * 60

    later = now.replace(hour=22, minute=45)
    assert runtime._seconds_until_diary(later) == 23 * 3600 + 45 * 60


def test_seconds_until_diary_requires_enabled_and_valid_time(tmp_path) -> None:
    now = datetime(2026, 10, 19, 22, 0, tzinfo=_TZ)
    assert _runtime(tmp_path, dynamic_diary_enabled=False)._seconds_until_diary(now) is None
    assert _runtime(tmp_path, dynamic_diary_time="25:00")._seconds_until_diary(now) is None
    assert _runtime(tmp_path, dynamic_diary_time="")._seconds_until_diary(now) is None


async def test_diary_loop_survives_failure_and_stops_when_unscheduled(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    delays = iter([0, None])
    runtime._seconds_until_diary = lambda now=None: next(delays)  # type: ignore[method-assign]
    calls: list[int] = []

    async def _boom() -> dict:
        calls.append(1)
        raise RuntimeError("boom")

    runtime.diary.run = _boom  # type: ignore[method-assign]
    await asyncio.wait_for(runtime._diary_loop(), timeout=5)
    assert calls == [1]


async def test_run_starts_diary_task_and_cancels_it_on_stop(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    started = asyncio.Event()

    async def _sleep_forever() -> None:
        started.set()
        await asyncio.Event().wait()

    runtime._diary_loop = _sleep_forever  # type: ignore[method-assign]
    task = asyncio.create_task(runtime.run())
    await asyncio.wait_for(started.wait(), timeout=5)
    assert runtime._diary_task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime._diary_task is None


async def test_run_does_not_start_diary_when_disabled(tmp_path) -> None:
    runtime = _runtime(tmp_path, dynamic_diary_enabled=False)
    task = asyncio.create_task(runtime.run())
    for _ in range(100):
        await asyncio.sleep(0.01)
        if runtime._started:
            break
    await asyncio.sleep(0.01)
    assert runtime._diary_task is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task



async def test_diary_loop_flushes_summary_before_run(tmp_path, monkeypatch) -> None:
    import neobot_app.bilibili.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "DIARY_SUMMARY_SETTLE_SECONDS", 0)
    runtime = _runtime(tmp_path)
    delays = iter([0, None])
    runtime._seconds_until_diary = lambda now=None: next(delays)  # type: ignore[method-assign]
    flushed: list[bool] = []
    order: list[str] = []

    class _Summary:
        async def flush_all(self, timeout=0):
            flushed.append(True)
            order.append("summary")

    async def _run() -> dict:
        order.append("diary")
        return {"ok": True}

    runtime.set_archive_summary_service(_Summary())
    runtime.diary.run = _run  # type: ignore[method-assign]
    await asyncio.wait_for(runtime._diary_loop(), timeout=5)

    assert flushed == [True]
    assert order == ["summary", "diary"]


def test_apply_config_updates_live_mention_names(tmp_path) -> None:
    """热重载必须更新直播间 @ 识别名单：文档承诺名单类配置「下次读取即生效」。"""
    runtime = _runtime(tmp_path)
    assert runtime.live_interactor._mention_names == ()

    runtime.apply_config(
        SimpleNamespace(
            bilibili=SimpleNamespace(
                cookie_file=str(tmp_path / "cookies.json"),
                live_interaction_mention_names=["前女友", "  "],
            ),
            bot=SimpleNamespace(nick_name="", bot_data=""),
        )
    )

    assert runtime.live_interactor._mention_names == ("前女友",)
    assert "前女友" in runtime.live_interactor._known_bot_names()
