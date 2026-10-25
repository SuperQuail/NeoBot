"""BilibiliRuntime 测试：每日动态日记的排期、跨天、失败隔离与取消。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from neobot_app.bilibili.runtime import BilibiliRuntime

_TZ = timezone(timedelta(hours=8))


def _config(tmp_path, **overrides) -> SimpleNamespace:
    values = {
        "cookie_file": str(tmp_path / "cookies.json"),
        "dynamic_diary_enabled": True,
        "dynamic_diary_time": "22:30",
        "comment_reply_enabled": False,
        "private_message_enabled": False,
        "poll_interval_seconds": 1800,
    }
    values.update(overrides)
    return SimpleNamespace(
        bilibili=SimpleNamespace(**values),
        bot=SimpleNamespace(nick_name="", bot_data=""),
    )


def _runtime(tmp_path, **overrides) -> BilibiliRuntime:
    config = _config(tmp_path, **overrides)
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


def test_invalid_diary_time_warns_only_once(tmp_path) -> None:
    """时间配置非法时日记会每分钟重排一次；提醒不能每分钟刷屏。"""
    warnings: list[str] = []

    class _RecordingLogger:
        def bind(self, **_kw):
            return self

        def debug(self, msg, **_kw):
            pass

        def info(self, msg, **_kw):
            pass

        def warning(self, msg, **_kw):
            warnings.append(str(msg))

        error = exception = warning

    runtime = BilibiliRuntime(
        config=_config(tmp_path, dynamic_diary_time="25:00"),
        provider=None,
        archive_service=None,
        uow_factory=None,
        command_service=None,
        logger=_RecordingLogger(),
    )
    now = datetime(2026, 10, 19, 22, 0, tzinfo=_TZ)

    assert runtime._seconds_until_diary(now) is None
    assert runtime._seconds_until_diary(now) is None
    assert len(warnings) == 1


async def test_diary_loop_survives_failure_and_waits_when_unscheduled(
    tmp_path, monkeypatch
) -> None:
    """单次失败只记日志；未启用/配置非法不再永久退出，等热重载改配置。"""
    import neobot_app.bilibili.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "DIARY_IDLE_SECONDS", 0.01)
    runtime = _runtime(tmp_path)
    delays = iter([0])
    runtime._seconds_until_diary = lambda now=None: next(delays, None)  # type: ignore[method-assign]
    calls: list[int] = []

    async def _boom() -> dict:
        calls.append(1)
        raise RuntimeError("boom")

    runtime.diary.run = _boom  # type: ignore[method-assign]
    task = asyncio.create_task(runtime._diary_loop())
    for _ in range(200):
        await asyncio.sleep(0.01)
        if calls:
            break
    await asyncio.sleep(0.05)

    assert calls == [1]
    assert not task.done()  # 排期为空时继续等配置，而不是退出
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


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
    monkeypatch.setattr(runtime_module, "DIARY_IDLE_SECONDS", 0.01)
    runtime = _runtime(tmp_path)
    delays = iter([0])
    runtime._seconds_until_diary = lambda now=None: next(delays, None)  # type: ignore[method-assign]
    flushed: list[bool] = []
    order: list[str] = []
    ran = asyncio.Event()

    class _Summary:
        async def flush_all(self, timeout=0):
            flushed.append(True)
            order.append("summary")

    async def _run() -> dict:
        order.append("diary")
        ran.set()
        return {"ok": True}

    runtime.set_archive_summary_service(_Summary())
    runtime.diary.run = _run  # type: ignore[method-assign]
    task = asyncio.create_task(runtime._diary_loop())
    await asyncio.wait_for(ran.wait(), timeout=5)

    assert flushed == [True]
    assert order == ["summary", "diary"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_apply_config_creates_and_cancels_diary_task(tmp_path, monkeypatch) -> None:
    """热重载 diary 开关必须真的起停 _diary_task，否则改了配置要重启才生效。"""
    runtime = _runtime(tmp_path, dynamic_diary_enabled=False)
    started: list[int] = []

    async def _sleep_forever() -> None:
        started.append(1)
        await asyncio.Event().wait()

    async def _fake_live_start() -> None:
        runtime.live_interactor._running = True

    monkeypatch.setattr(runtime, "_diary_loop", _sleep_forever)
    monkeypatch.setattr(runtime.live_interactor, "start", _fake_live_start)
    await runtime.start()
    assert runtime._diary_task is None

    runtime.apply_config(_config(tmp_path, dynamic_diary_enabled=True))
    assert runtime._diary_task is not None
    for _ in range(100):
        await asyncio.sleep(0.01)
        if started:
            break
    assert started == [1]

    runtime.apply_config(_config(tmp_path, dynamic_diary_enabled=False))
    assert runtime._diary_task is None
    await runtime.stop()


async def test_live_start_failure_resets_running_and_retries(tmp_path, monkeypatch) -> None:
    """start() 半途失败会留下 _running=True；必须复位，否则 ensure_started 永远直接返回。"""
    import neobot_app.bilibili.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_LIVE_RETRY_DELAYS", (0.01, 0.01))
    runtime = _runtime(tmp_path, dynamic_diary_enabled=False)
    calls: list[int] = []

    async def _start() -> None:
        calls.append(1)
        runtime.live_interactor._running = True  # start() 先置位再失败
        if len(calls) == 1:
            raise RuntimeError("启动炸了")

    monkeypatch.setattr(runtime.live_interactor, "start", _start)
    await runtime.start()

    assert calls == [1]
    assert runtime.live_interactor._running is False

    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(calls) >= 2:
            break
    assert calls == [1, 1]  # 退避后自动重试
    assert runtime.live_interactor._running is True
    await runtime.stop()


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


async def test_handle_bili_status_refreshes_and_sends_card(tmp_path, monkeypatch) -> None:
    import neobot_app.bilibili.account_card as account_card

    runtime = _runtime(tmp_path)
    calls: list[object] = []

    async def _refresh() -> bool:
        calls.append("refresh")
        return True

    async def _card(ctx, service, *, extra_rows=None):
        calls.append(("card", extra_rows))
        return "卡片"

    monkeypatch.setattr(runtime.service, "refresh", _refresh)
    monkeypatch.setattr(account_card, "send_account_card", _card)

    result = await runtime._handle_bili(SimpleNamespace(args=["status"], permission=0))

    assert result == "卡片"
    assert calls[0] == "refresh"
    rows = dict(calls[1][1])
    assert rows["评论回复"] == "关"
    assert rows["私信回复"] == "关"


def _bili_ctx(allowed: bool) -> SimpleNamespace:
    permissions = SimpleNamespace(can=lambda user_id, level: allowed)
    return SimpleNamespace(
        args=["dynamic", "hi"],
        user_id=1,
        service=SimpleNamespace(permissions=permissions),
    )


async def test_handle_bili_dynamic_requires_sub_admin(tmp_path) -> None:
    runtime = _runtime(tmp_path)

    assert "次级管理员" in await runtime._handle_bili(_bili_ctx(False))


async def test_handle_bili_dynamic_allows_sub_admin(tmp_path) -> None:
    runtime = _runtime(tmp_path)

    result = await runtime._handle_bili(_bili_ctx(True))

    assert "次级管理员" not in result
