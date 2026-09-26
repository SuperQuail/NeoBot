"""Real lifecycle/CLI, fake IO only: no real bot, network, signals or execv."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from neobot_app import cli
from neobot_app.bootstrap import _standby_runtime as lifecycle
from neobot_app.bootstrap._standby_runtime import StandbyController
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.process_restart import ProcessRestartSignal
from neobot_app.runtime.standby_service import StandbyService


class IO:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.running = False

    async def start(self) -> None:
        self.starts += 1
        self.running = True

    async def stop(self) -> None:
        self.stops += 1
        self.running = False


class Ingress:
    def __init__(self) -> None:
        self.ready = asyncio.Event()
        self.stops = 0

    def start(self) -> None:
        self.ready.set()

    def stop(self) -> None:
        self.stops += 1


class BlockedCleanup:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def shutdown(self) -> None:
        self.calls += 1
        self.entered.set()
        await self.release.wait()


def app(*, adapter=None, cleanup=None, chat=None, plugins=None) -> NeoBotApplication:
    return NeoBotApplication(
        adapter=adapter or IO(),
        chat_stream=chat or SimpleNamespace(initialize=AsyncMock()),
        event_ingress=Ingress(),
        file_server=IO(),
        reply_orchestrator=cleanup,
        plugin_runtime=plugins,
        owns_plugins=False,
    )


def controller(service, factory, *, initial=None, signal=None, adapter=None):
    result = StandbyController(
        standby_service=service,
        runtime_factory=factory,
        initial_application=initial,
        restart_signal=signal,
        adapter=adapter,
    )
    service.set_hooks(on_enter=result.enter, on_resume=result.resume, on_onebot_change=result.set_onebot)
    return result


async def bounded(task, seconds=1):
    done, _ = await asyncio.wait((task,), timeout=seconds)
    assert done, "operation did not return within its bounded test budget"
    return await task


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0.001)


async def finish_controller(ctrl):
    if ctrl._operation is not None:
        await asyncio.gather(ctrl._operation, return_exceptions=True)
    ok, detail = await ctrl.shutdown()
    assert ok, detail


def signal_handler_seams() -> list[type]:
    """所有真正实现 add_signal_handler 的事件循环类。

    只有 Windows 会回落到 BaseEventLoop 那套 NotImplementedError 实现；Unix 上
    由 _UnixSelectorEventLoop 覆盖。只 patch 基类时在 Linux 上是静默失效的：
    回调进不了测试的 handlers（KeyError），而且会真的往运行中的 loop 装
    SIGINT/SIGTERM。这里把子类树里自己实现了该方法的类一并找出来。
    """
    seams: list[type] = [asyncio.BaseEventLoop]
    pending = list(asyncio.BaseEventLoop.__subclasses__())
    while pending:
        candidate = pending.pop()
        if "add_signal_handler" in vars(candidate):
            seams.append(candidate)
        pending.extend(candidate.__subclasses__())
    return seams


def capture_stop_handlers(monkeypatch) -> dict:
    """把 cli 注册的停止回调收进字典，供测试手动触发。"""
    handlers: dict = {}

    def record(_loop, sig, callback, *args):
        handlers[sig] = callback

    for seam in signal_handler_seams():
        monkeypatch.setattr(seam, "add_signal_handler", record)
    return handlers


@pytest.fixture(autouse=True)
def no_process_operations(monkeypatch):
    monkeypatch.setattr(cli.os, "execv", Mock(side_effect=AssertionError("no execv")))
    monkeypatch.setattr(cli.signal, "signal", Mock())
    stub = Mock()
    for seam in signal_handler_seams():
        monkeypatch.setattr(seam, "add_signal_handler", stub)


def wire_cli(monkeypatch, initial, standby, signal):
    plugin = SimpleNamespace(
        load_registered=AsyncMock(), start_all=AsyncMock(), stop_all=AsyncMock(),
        agent_registry=SimpleNamespace(close=AsyncMock()),
    )
    initial._plugin_runtime = plugin
    mapping = {
        "standby_service": standby,
        "process_restart": signal,
        "adapter": initial.adapter,
        "plugin_runtime": plugin,
    }
    factory = Mock(return_value=initial)
    monkeypatch.setattr(cli, "enable_core_reuse", lambda: None)
    monkeypatch.setattr(cli, "create_application", factory)
    monkeypatch.setattr(cli, "get_cached_core", lambda key: mapping.get(key))
    return plugin, factory


async def test_signal_handler_interception_covers_the_running_loop():
    """回归：拦截必须覆盖运行中 loop 实际解析到的那个 add_signal_handler。

    Unix 上 _UnixSelectorEventLoop 覆盖了基类实现，只 patch BaseEventLoop 会静默
    失效：回调进不了测试的 handlers（CI 上表现为 KeyError），还会真的把
    SIGINT/SIGTERM 注册到进程上。
    """
    loop_class = type(asyncio.get_running_loop())
    resolved = next(cls for cls in loop_class.__mro__ if "add_signal_handler" in vars(cls))
    assert resolved in signal_handler_seams()


async def test_signal_is_durable_thread_notified_and_coalesces():
    signal = ProcessRestartSignal()
    waiter = asyncio.create_task(signal.wait())
    await until(lambda: bool(signal._waiters))
    thread = threading.Thread(target=lambda: (signal.request(), signal.request()))
    thread.start()
    thread.join()
    await bounded(waiter)
    assert signal.requested
    await bounded(asyncio.create_task(signal.wait()))
    assert not signal._waiters

    unused = ProcessRestartSignal()
    waiter = asyncio.create_task(unused.wait())
    await until(lambda: bool(unused._waiters))
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert not unused._waiters


async def test_running_cli_wakes_real_run_forever_and_stops_core_once(monkeypatch):
    initial = app()
    signal = ProcessRestartSignal()
    plugin, factory = wire_cli(monkeypatch, initial, StandbyService(), signal)
    task = asyncio.create_task(cli.run())
    try:
        await initial.event_ingress.ready.wait()
        await until(lambda: any(t.get_name() == "neobot-run-forever" for t in asyncio.all_tasks()))
        assert not task.done() and not initial._shutdown_event.is_set()
        signal.request()
        signal.request()
        assert await bounded(task) is True
        assert initial._shutdown_event.is_set()
        assert initial._started is False
        assert initial.adapter.stops == initial.file_server.stops == 1
        plugin.load_registered.assert_awaited_once()
        plugin.start_all.assert_awaited_once()
        plugin.stop_all.assert_awaited_once()
        plugin.agent_registry.close.assert_awaited_once()
        factory.assert_called_once()
        assert not signal._waiters
    finally:
        signal.request()
        await bounded(task)


@pytest.mark.parametrize("failed_start", [False, True])
async def test_cli_restart_in_standby_or_failed_startup(monkeypatch, failed_start):
    initial = app(chat=SimpleNamespace(initialize=AsyncMock(side_effect=RuntimeError("bad startup"))))
    service = StandbyService(start_in_standby=not failed_start, connect_onebot=False)
    signal = ProcessRestartSignal()
    plugin, factory = wire_cli(monkeypatch, initial, service, signal)
    task = asyncio.create_task(cli.run())
    try:
        await until(lambda: initial._cleanup_complete)
        assert not task.done()
        assert service.is_standby()
        signal.request()
        assert await bounded(task) is True
        assert not initial._started
        assert factory.call_count == 1
        plugin.stop_all.assert_awaited_once()
    finally:
        signal.request()
        await bounded(task)


async def test_normal_signal_stop_wins_during_restart_cleanup(monkeypatch):
    cleanup = BlockedCleanup()
    initial = app(cleanup=cleanup)
    signal = ProcessRestartSignal()
    handlers = capture_stop_handlers(monkeypatch)
    wire_cli(monkeypatch, initial, StandbyService(), signal)
    task = asyncio.create_task(cli.run())
    try:
        await initial.event_ingress.ready.wait()
        signal.request()
        await cleanup.entered.wait()
        handlers[cli.signal.SIGINT]()
        cleanup.release.set()
        assert await bounded(task) is False
    finally:
        cleanup.release.set()
        signal.request()
        await bounded(task)


@pytest.mark.parametrize("outer_watchdog", [False, True])
async def test_stop_timeout_retains_generation_and_allows_retry_only_after_cleanup(monkeypatch, outer_watchdog):
    monkeypatch.setattr(lifecycle, "STOP_TIMEOUT_SECONDS", 10 if outer_watchdog else 0.01)
    service = StandbyService(connect_onebot=False, resume_timeout=0.01 if outer_watchdog else 1)
    cleanup = BlockedCleanup()
    old = app(cleanup=cleanup)
    fresh = app()
    factory = Mock(return_value=fresh)
    ctrl = controller(service, factory, initial=old)
    await ctrl.start()
    try:
        task = asyncio.create_task(service.resume())
        await cleanup.entered.wait()
        # Mimic a cancellation hitting NeoBotApplication.stop's shield loop.
        ctrl._stopping_task.cancel()
        ok, detail = await bounded(task)
        assert not ok and "超时" in detail
        assert service._transition
        assert service.status()["state"] not in ("running", "standby")
        assert ctrl._app is old and ctrl.application is None
        assert not ctrl._stopping_task.done()
        assert old._started
        factory.assert_not_called()
        for action in (service.enter, service.resume, lambda: service.set_connect_onebot(True)):
            ok, detail = await bounded(asyncio.create_task(action()))
            assert not ok and "清理" in detail
        cleanup.release.set()
        await asyncio.gather(ctrl._operation, return_exceptions=True)
        await until(lambda: not service._transition)
        # The artificially cancelled stop deferred cancellation until cleanup
        # completed. A retry must handle that retained reference safely.
        service._resume_timeout = 1
        ok, detail = await service.resume()
        assert ok, detail
        assert ctrl.application is fresh and not old._started
        assert factory.call_count == 1
    finally:
        cleanup.release.set()
        await finish_controller(ctrl)


async def test_rebuilding_restart_aborts_future_publication_and_waits_for_old_cleanup(monkeypatch, capsys):
    monkeypatch.setattr(lifecycle, "STOP_TIMEOUT_SECONDS", 0.01)
    service = StandbyService(connect_onebot=False)
    signal = ProcessRestartSignal()
    cleanup = BlockedCleanup()
    old = app(cleanup=cleanup)
    factory = Mock(return_value=app())
    ctrl = controller(service, factory, initial=old, signal=signal)
    await ctrl.start()
    entry = asyncio.create_task(cli.run_entry_loop(
        controller=ctrl, standby_service=service, restart_signal=signal,
        state={"stopping": False}, poll_interval=0.005,
    ))
    rebuild = asyncio.create_task(service.resume())
    try:
        await cleanup.entered.wait()
        ok, _ = await bounded(rebuild)
        assert not ok
        signal.request()
        signal.request()
        await until(lambda: ctrl.exiting)
        await asyncio.sleep(0.025)
        assert not entry.done(), "restart cannot authorize exec while cleanup is pending"
        assert "强制重启" in capsys.readouterr().err
        factory.assert_not_called()
        cleanup.release.set()
        assert await bounded(entry) is True
        factory.assert_not_called()
        assert not old._started and ctrl.application is None
        assert not signal._waiters
    finally:
        cleanup.release.set()
        signal.request()
        await bounded(rebuild)
        await bounded(entry)


@pytest.mark.parametrize("late_success", [False, True])
async def test_start_timeout_owns_rollback_or_late_success_without_orphan(monkeypatch, late_success):
    monkeypatch.setattr(lifecycle, "START_TIMEOUT_SECONDS", 0.01)
    service = StandbyService(start_in_standby=True, connect_onebot=False)
    blocked = asyncio.Event()
    release = asyncio.Event()

    async def initialize():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            blocked.set()
            if late_success:
                await release.wait()  # Deliberately suppress cancellation.
            else:
                raise

    initial = app(chat=SimpleNamespace(initialize=initialize))
    if not late_success:
        async def blocked_file_stop():
            blocked.set()
            await release.wait()
            initial.file_server.running = False
            initial.file_server.stops += 1
        initial.file_server.stop = blocked_file_stop
    next_app = app()
    factory = Mock(side_effect=[initial, next_app])
    ctrl = controller(service, factory)
    try:
        action = asyncio.create_task(service.resume())
        await blocked.wait()
        ok, detail = await bounded(action)
        assert not ok and "starting" in detail
        assert service._transition and ctrl._starting_app is initial
        assert ctrl.application is None
        ok, _ = await bounded(asyncio.create_task(service.resume()))
        assert not ok and factory.call_count == 1
        release.set()
        await asyncio.gather(ctrl._operation, return_exceptions=True)
        await until(lambda: not service._transition)
        assert ctrl.application is None and not initial._started
        assert initial.file_server.running is False
        assert initial._cleanup_complete
        ok, detail = await service.resume()
        assert ok, detail
        assert ctrl.application is next_app
    finally:
        release.set()
        await finish_controller(ctrl)


async def test_restart_during_initial_start_cancels_and_disposes_late_runtime(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def initialize():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    initial = app(chat=SimpleNamespace(initialize=initialize))
    service = StandbyService(connect_onebot=False)
    signal = ProcessRestartSignal()
    _, factory = wire_cli(monkeypatch, initial, service, signal)
    task = asyncio.create_task(cli.run())
    try:
        await entered.wait()
        signal.request()
        await until(lambda: service._lifecycle()["pending"])
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        assert await bounded(task) is True
        assert not initial._started and not initial.file_server.running
        assert factory.call_count == 1
        assert not signal._waiters
    finally:
        release.set()
        signal.request()
        await bounded(task)


async def test_watchdog_retains_cancel_resistant_hook_without_late_promotion():
    release = asyncio.Event()
    cancelled = asyncio.Event()

    async def resume():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
        return True, "late success must not promote state"

    service = StandbyService(start_in_standby=True, on_resume=resume, resume_timeout=0.01)
    try:
        ok, detail = await bounded(asyncio.create_task(service.resume()))
        assert not ok and "超时" in detail
        await cancelled.wait()
        assert service._transition
        assert service.status()["state"] == "transitioning"
        ok, _ = await service.resume()
        assert not ok
    finally:
        release.set()
        await service._pending_action
    assert service.is_standby() and not service._transition


async def test_restart_during_core_plugin_startup_keeps_ownership(monkeypatch):
    initial = app()
    service = StandbyService(connect_onebot=False)
    signal = ProcessRestartSignal()
    plugins, factory = wire_cli(monkeypatch, initial, service, signal)
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def start_plugins():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()

    plugins.start_all.side_effect = start_plugins
    task = asyncio.create_task(cli.run())
    try:
        await entered.wait()
        signal.request()
        await cancelled.wait()
        assert not task.done()
        assert initial.file_server.starts == 0
        release.set()
        assert await bounded(task) is True
        assert initial._cleanup_complete and not initial._started
        assert factory.call_count == 1
        plugins.stop_all.assert_awaited_once()
        assert not signal._waiters
    finally:
        release.set()
        signal.request()
        await bounded(task)


async def test_normal_stop_during_final_core_cleanup_revokes_restart(monkeypatch):
    signal = ProcessRestartSignal()
    signal.request()
    initial = app()
    plugins, _ = wire_cli(monkeypatch, initial, StandbyService(), signal)
    handlers = capture_stop_handlers(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def stop_plugins():
        entered.set()
        await release.wait()

    plugins.stop_all.side_effect = stop_plugins
    task = asyncio.create_task(cli.run())
    try:
        await entered.wait()
        handlers[cli.signal.SIGINT]()
        release.set()
        assert await bounded(task) is False
        assert not initial._started and not signal._waiters
    finally:
        release.set()
        await bounded(task)


async def test_normal_stop_removes_unnotified_core_watcher(monkeypatch):
    initial = app()
    signal = ProcessRestartSignal()
    wire_cli(monkeypatch, initial, StandbyService(), signal)
    handlers = capture_stop_handlers(monkeypatch)
    task = asyncio.create_task(cli.run())
    try:
        await initial.event_ingress.ready.wait()
        await until(lambda: bool(signal._waiters))
        handlers[cli.signal.SIGTERM]()
        assert await bounded(task) is False
        assert not signal.requested and not signal._waiters
        assert not initial._started
    finally:
        handlers[cli.signal.SIGTERM]()
        await bounded(task)


@pytest.mark.parametrize("previous", [False, True])
@pytest.mark.parametrize("shutdown", [False, True])
async def test_late_onebot_toggle_compensates_uncommitted_preference(monkeypatch, previous, shutdown):
    monkeypatch.setattr(lifecycle, "STOP_TIMEOUT_SECONDS", 0.01)
    entered, release = asyncio.Event(), asyncio.Event()

    class Adapter(IO):
        block = False

        async def change(self, desired):
            if self.block:
                self.block = False
                entered.set()
                await release.wait()
            self.running = desired

        async def start(self):
            self.starts += 1
            await self.change(True)

        async def stop(self):
            self.stops += 1
            await self.change(False)

    adapter = Adapter()
    service = StandbyService(start_in_standby=True, connect_onebot=previous)
    ctrl = controller(service, Mock(), adapter=adapter)
    await ctrl.start()
    adapter.block = True
    try:
        toggle = asyncio.create_task(service.set_connect_onebot(not previous))
        await entered.wait()
        ok, detail = await bounded(toggle)
        assert not ok and "超时" in detail
        assert service._transition
        assert service.connect_onebot is previous
        if shutdown:
            ctrl.request_shutdown()
        release.set()
        await ctrl.wait_for_idle()
        assert not service._transition
        assert adapter.running is (False if shutdown else previous)
        assert ctrl._adapter_running is adapter.running
        if not shutdown:
            ok, detail = await service.set_connect_onebot(previous)
            assert ok, detail
            assert adapter.running is previous
        elif previous:
            assert adapter.starts == 1, "shutdown must not reconnect the old True preference"
    finally:
        release.set()
        await finish_controller(ctrl)


@pytest.mark.parametrize("cancel_target", ["hook", "caller"])
@pytest.mark.parametrize("delay_turns", range(11))
async def test_cancel_at_start_completion_retires_uncommitted_published_app(delay_turns, cancel_target):
    service = StandbyService(start_in_standby=True, connect_onebot=False)
    initial, fresh = app(), app()
    ctrl = controller(service, Mock(side_effect=[initial, fresh]))
    hooks = []

    async def file_start():
        hook = service._pending_action
        hooks.append(hook)
        target = hook if cancel_target == "hook" else outer
        loop = asyncio.get_running_loop()

        def cancel_after(turns):
            if turns:
                loop.call_soon(cancel_after, turns - 1)
            else:
                target.cancel()

        asyncio.current_task().add_done_callback(lambda _done: cancel_after(delay_turns))

    initial.file_server.start = file_start
    outer = asyncio.create_task(service.resume())
    try:
        try:
            ok, detail = await outer
        except asyncio.CancelledError:
            # The service caller can finish before a cancelled hook has handled
            # its own cancellation. Drain both ownership layers explicitly.
            await asyncio.gather(*hooks, return_exceptions=True)
            await ctrl.wait_for_idle()
            assert ctrl.application is None and ctrl._app is None
            assert not initial._started
            assert service.is_standby() and not service._transition
            assert initial.event_ingress.stops == 1
            ok, detail = await service.resume()
            assert ok, detail
            assert ctrl.application is fresh
            ctrl.abort_transition(hooks[0])
            assert ctrl.application is fresh, "stale cancellation must not touch the new generation"
        else:
            # Cancellation after the caller returned cannot revoke an already
            # committed result; before that, every await (including finally's
            # waiter cleanup) must retire the uncommitted runtime.
            assert delay_turns >= 6
            assert ok, detail
            assert ctrl.application is initial and initial._started
            assert not service.is_standby()
    finally:
        await asyncio.gather(outer, *hooks, return_exceptions=True)
        await finish_controller(ctrl)


@pytest.mark.parametrize("previous", [False, True])
@pytest.mark.parametrize("shutdown", [False, True])
@pytest.mark.parametrize("cancel_target", ["hook", "caller"])
@pytest.mark.parametrize("delay_turns", range(11))
async def test_cancel_completed_onebot_toggle_before_preference_commit(
    previous, shutdown, cancel_target, delay_turns
):
    hooks = []
    fired = asyncio.Event()

    class Adapter(IO):
        capture = False

        async def change(self, desired):
            self.running = desired
            if not self.capture:
                return
            self.capture = False
            hook = service._pending_action
            hooks.append(hook)
            target = hook if cancel_target == "hook" else outer
            loop = asyncio.get_running_loop()

            def cancel_after(turns):
                if turns:
                    loop.call_soon(cancel_after, turns - 1)
                else:
                    if shutdown:
                        ctrl.request_shutdown()
                    target.cancel()
                    fired.set()

            asyncio.current_task().add_done_callback(lambda _done: cancel_after(delay_turns))

        async def start(self):
            self.starts += 1
            await self.change(True)

        async def stop(self):
            self.stops += 1
            await self.change(False)

    adapter = Adapter()
    service = StandbyService(start_in_standby=True, connect_onebot=previous)
    ctrl = controller(service, Mock(), adapter=adapter)
    await ctrl.start()
    adapter.capture = True
    outer = asyncio.create_task(service.set_connect_onebot(not previous))
    try:
        cancelled = False
        try:
            ok, detail = await outer
        except asyncio.CancelledError:
            cancelled = True
        await fired.wait()
        await asyncio.gather(*hooks, return_exceptions=True)
        await ctrl.wait_for_idle()
        if cancelled:
            assert service.connect_onebot is previous
            assert adapter.running is (False if shutdown else previous)
            assert not service._transition
            if shutdown and previous:
                assert adapter.starts == 1, "shutdown must not compensate by reconnecting"
        else:
            assert ok, detail
            assert service.connect_onebot is not previous
        assert ctrl._adapter_running is adapter.running
    finally:
        await asyncio.gather(outer, *hooks, return_exceptions=True)
        await finish_controller(ctrl)


async def test_late_queued_runner_never_restarts_a_retired_generation():
    service = StandbyService(connect_onebot=False)
    runtime = app()
    ctrl = controller(service, Mock(), initial=runtime)
    await ctrl.start()
    # Capture exactly what the entry loop would queue, then let retirement win
    # the scheduling race before run_forever first executes.
    queued = runtime.run_forever()
    try:
        ok, detail = await service.enter()
        assert ok, detail
        await bounded(asyncio.create_task(queued))
        assert runtime.adapter.starts == 1
        assert not runtime._started and ctrl.application is None
    finally:
        queued.close()
        await finish_controller(ctrl)


async def test_entry_tracks_new_generation_instead_of_exiting_after_fast_rebuild():
    service = StandbyService(connect_onebot=False)
    old, fresh = app(), app()
    signal = ProcessRestartSignal()
    ctrl = controller(service, lambda: fresh, initial=old, signal=signal)
    await ctrl.start()
    entry = asyncio.create_task(cli.run_entry_loop(
        controller=ctrl, standby_service=service, restart_signal=signal,
        state={"stopping": False}, poll_interval=0.005,
    ))
    try:
        await until(lambda: any(t.get_name() == "neobot-run-forever" for t in asyncio.all_tasks()))
        ok, detail = await service.resume()
        assert ok, detail
        await fresh.event_ingress.ready.wait()
        await asyncio.sleep(0.015)
        assert not entry.done() and fresh._started
        signal.request()
        assert await bounded(entry) is True
    finally:
        signal.request()
        await bounded(entry)
