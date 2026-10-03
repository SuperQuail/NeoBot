"""Serial lifecycle orchestration; timed-out work remains owned until it settles.

The controller never treats cancellation or a timeout as proof of shutdown. Core
plugins are owned by the CLI; the runtime stops its adapter before standby may
reconnect the same adapter. No replacement generation is built during cleanup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Awaitable
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

RuntimeFactory = Callable[[], Any]
STOP_TIMEOUT_SECONDS = 20.0
START_TIMEOUT_SECONDS = 120.0


class StandbyController:
    def __init__(
        self,
        *,
        standby_service: Any,
        runtime_factory: RuntimeFactory,
        adapter: Any = None,
        logger: Logger | None = None,
        initial_application: Any = None,
        restart_signal: Any = None,
    ) -> None:
        self._standby = standby_service
        self._factory = runtime_factory
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._app: Any = None
        self._initial = initial_application
        self._adapter_running = False
        self._restart_signal = restart_signal
        self._shutdown_requested = False
        self._operation: asyncio.Task | None = None
        self._starting_app: Any = None
        self._starting_task: asyncio.Task | None = None
        self._stopping_task: asyncio.Task | None = None
        self._phase = "idle"
        self._failure = ""
        self._aborted = False
        #: 调用方已撤销本次过渡（外层观察窗口到点 / HTTP 任务被取消）。就此发布的
        #: 新代际没人认领：服务不会提交 RUNNING，代际本身也拿不到 run_forever 的入口
        #: 循环。置位后本次过渡只允许收尾，不再发布第二代。
        self._caller_revoked = False
        self._attention = asyncio.Event()
        self._caller_task: asyncio.Task | None = None
        self._cancel_transition: Callable[[], None] | None = None
        standby_service.set_lifecycle_status(self.lifecycle_status, self.abort_transition)

    @property
    def application(self) -> Any:
        """Only a fully started, non-retiring generation may be run by the CLI."""
        return self._app if self._phase == "running" and not self.exiting and not self._aborted else None

    @property
    def exiting(self) -> bool:
        return self._shutdown_requested or bool(
            self._restart_signal is not None and self._restart_signal.requested
        )

    def lifecycle_status(self) -> dict[str, Any]:
        return {
            "pending": self._operation is not None and not self._operation.done(),
            "phase": self._phase,
            "detail": self._failure,
        }

    def _pending_message(self) -> str:
        return self._failure or (
            f"运行时正在切换中（{self._phase}），尚未确认清理完成；请等待后重试。"
        )

    def _report_pending(self, timeout: float) -> None:
        """超时是有界诊断：仍置 `_aborted` 以撤销未提交的改动。

        置位不是「判死这一代」，而是「本次动作的结果不算数」——适配器切换这类动作
        的补偿（`set_onebot` 的 `on_abort`）靠它才能在超时后把未提交的连接状态
        收回来。但 `_aborted` **不能**被当成「不要重建」的判据：优雅关闭要跑记忆
        总结这类分钟级收尾，窗口到点只说明「比预期慢」，此时停机仍在推进。软重启
        的停机阶段必须忽略它（见 `resume`），否则就是「只停不重启」。
        """
        self._aborted = True
        self._failure = (
            f"运行时 {self._phase} 超时（观察窗口 {timeout:g}s）："
            "清理仍在进行，未启动第二个运行时。"
            "清理完成后本操作会继续收尾；进程重启请求仍可接受，但若优雅关闭持续卡住，"
            "需手动处理或显式强制重启进程（不会自动强杀）。"
        )
        self._logger.error(self._failure)
        self._attention.set()

    def _abort_operation(self, *, stop_runtime: bool = True) -> None:
        self._aborted = True
        for app in ((self._app, self._starting_app) if stop_runtime else ()):
            request = getattr(app, "request_stop", None)
            if callable(request):
                request()
        task = self._starting_task
        if task is not None and not task.done() and not task.cancelling():
            task.cancel()

    def request_shutdown(self) -> None:
        """Synchronous shutdown delivery; always resolve the current generation."""
        self._shutdown_requested = True
        self._abort_operation()

    def abort_transition(self, caller: asyncio.Task) -> None:
        """Revoke a hook result until the service commits it, even if done.

        The caller identity prevents an old completion/cancellation from
        revoking a newer transition. Task.cancel() alone cannot revoke a done
        hook during the outer service's final await/commit boundary.
        """
        if self._caller_task is caller and self._cancel_transition is not None:
            self._caller_revoked = True
            self._cancel_transition()

    async def _perform(
        self,
        action: Callable[[], Awaitable[tuple[bool, str]]],
        *,
        shutdown: bool = False,
        on_abort: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[bool, str]:
        if self._operation is not None and not self._operation.done():
            return False, self._pending_message()
        if self.exiting and not shutdown:
            return False, "进程正在关闭或等待重启，不再启动新的运行时。"
        self._aborted = False
        self._caller_revoked = False
        self._failure = ""
        self._attention.clear()
        self._caller_task = asyncio.current_task()

        async def compensate() -> None:
            if on_abort is not None:
                await on_abort()
            elif self._app is not None:
                await self._stop_runtime()

        async def owned_action() -> tuple[bool, str]:
            try:
                return await action()
            finally:
                # Cancellation can land after start() published but before the
                # awaiting service committed RUNNING. Retire that generation,
                # rather than leaving a started app hidden behind standby.
                if self._aborted:
                    await compensate()

        task = asyncio.create_task(owned_action(), name="neobot-lifecycle-transition")
        self._operation = task

        def finished(done: asyncio.Task) -> None:
            if self._operation is not done:
                return
            try:
                done.result()
            except BaseException as exc:
                failed_phase = self._phase
                self._phase = "failed"
                self._failure = f"运行时 {failed_phase} 失败：{type(exc).__name__}: {exc}；请检查日志后重试。"
                self._logger.error(self._failure)
            else:
                if on_abort is not None and not self.exiting:
                    self._aborted = False
                self._phase = "running" if self._app is not None and not self.exiting else "idle"

        def cancel_transition() -> None:
            if self._operation is not task:
                return
            self._abort_operation(stop_runtime=on_abort is None or self.exiting)
            if task.done() and (self._app is not None or on_abort is not None):
                # Retain compensation for a result completed but not committed
                # by the caller. No await may precede hiding this generation.
                self._phase = "onebot_rollback" if on_abort is not None else "stopping"
                retirement = asyncio.create_task(compensate(), name="neobot-aborted-transition-retire")
                self._operation = retirement
                retirement.add_done_callback(finished)

        self._cancel_transition = cancel_transition
        task.add_done_callback(finished)
        attention = asyncio.create_task(self._attention.wait())
        try:
            try:
                await asyncio.wait((task, attention), return_when=asyncio.FIRST_COMPLETED)
                if not task.done():
                    return False, self._pending_message()
                try:
                    return task.result()
                except Exception as exc:
                    return False, f"{self._phase}: {type(exc).__name__}: {exc}"
            finally:
                attention.cancel()
                await asyncio.gather(attention, return_exceptions=True)
        except asyncio.CancelledError:
            # The caller may be an HTTP task or the service watchdog. It does
            # not own this operation; abort its intent, not its cleanup task.
            cancel_transition()
            raise

    async def _wait_stage(
        self, task: asyncio.Task, timeout: float, *, prognostic: bool = True
    ) -> None:
        """等一个阶段结束；窗口到点是否上报由 `prognostic` 决定。

        `prognostic=True`（启动/适配器切换）：窗口到点就上报，让调用方尽早拿到有界
        失败，代价是「慢」会被当成失败——启动半成品确实该丢弃、适配器切换确实该补偿，
        所以这个代价是划算的。

        `prognostic=False`（停机）：停机慢只是慢。优雅关闭要跑记忆总结这类分钟级
        收尾，窗口必然先到；此时上报会让调用方在动作其实已经成功时把状态判成失败
        （软重启回报 pending、服务停在待机，而代际其实已经重建）。所以这里只记日志，
        等它真的做完；有界性交给调用方自己的外层窗口。
        """
        done, _ = await asyncio.wait((task,), timeout=timeout if timeout > 0 else None)
        if not done:
            if prognostic:
                self._report_pending(timeout)
                if task is self._starting_task:
                    self._abort_operation()
            else:
                self._logger.warning(
                    f"运行时 {self._phase} 超过观察窗口（{timeout:g}s）仍在收尾；"
                    "这是慢不是卡死，继续等它做完（记忆总结等关闭收尾可能耗时数分钟）。"
                )
        # This unbounded drain is OWNED by _operation. The caller already got a
        # bounded failure via _attention; no cancellation can discard resources.
        await asyncio.shield(task)

    async def start(self) -> tuple[bool, str]:
        initially_standby = self._standby.is_standby()

        async def startup() -> tuple[bool, str]:
            if initially_standby:
                await self._discard_initial()
                if not self.exiting and not self._aborted:
                    await self._sync_adapter(desired=bool(self._standby.connect_onebot))
                return not self._aborted, "以待机状态启动：仅保留核心服务。"
            await self._start_runtime()
            return self.application is not None, self._failure or "Bot 已启动。"

        return await self._perform(startup)

    async def enter(self) -> tuple[bool, str]:
        async def enter() -> tuple[bool, str]:
            await self._stop_runtime()
            if self._aborted or self.exiting:
                return False, self._pending_message()
            if not await self._sync_adapter(desired=bool(self._standby.connect_onebot)):
                return False, "运行时已停止，但待机 OneBot 连接切换失败；请检查日志。"
            return True, "bot 运行时已停止：只保留面板、配置与命令，/reboot 可软重启运行。"

        return await self._perform(enter)

    async def resume(self) -> tuple[bool, str]:
        async def resume() -> tuple[bool, str]:
            await self._stop_runtime()
            # 停机真的做完了，之前「比预期慢」的那份延迟诊断就失效了：清掉它，否则
            # owned_action 的 finally 会把下面刚发布的新代际当成未提交的代际补偿掉。
            self._aborted = False
            # 只认真正的退出意图。停机慢不否决重建 —— 那正是「只停不重启」的成因。
            if self.exiting:
                return False, self._pending_message()
            # 调用方已经撤销本次过渡（外层窗口到点 / HTTP 任务被取消）：这一代发出去
            # 也没人认领 —— 服务不会提交 RUNNING，也拿不到 run_forever 的入口循环。
            # 老老实实停在待机，让人重试；宁可少发一代，不发一代孤儿。
            if self._caller_revoked:
                return False, self._pending_message()
            await self._start_runtime()
            if self.application is None:
                return False, self._failure or "启动已中止，未发布新的运行时。"
            return True, "已按当前配置软重启运行（进程未重启，面板未断线）。"

        return await self._perform(resume)

    async def wait_for_idle(self) -> None:
        """Drain owned work, including cancellation-resistant rollback, on exit."""
        if self._operation is not None:
            await asyncio.shield(asyncio.gather(self._operation, return_exceptions=True))

    async def shutdown(self) -> tuple[bool, str]:
        self.request_shutdown()

        async def shutdown() -> tuple[bool, str]:
            await self._stop_runtime()
            if self._starting_app is not None:
                self._phase = "startup_cleanup"
                task = asyncio.create_task(self._dispose(self._starting_app))
                await self._wait_stage(task, STOP_TIMEOUT_SECONDS)
                self._starting_app = None
            await self._discard_initial()
            await self._sync_adapter(desired=False)
            return True, "运行时与适配器已确认停止。"

        return await self._perform(shutdown, shutdown=True)

    async def set_onebot(self, enabled: bool) -> tuple[bool, str]:
        previous = self._adapter_running

        async def compensate() -> None:
            # The service has not committed this toggle after cancellation or
            # timeout. A late IO completion must restore the old preference;
            # process shutdown overrides that preference with disconnected.
            await self._sync_adapter(desired=False if self.exiting else previous)
            if self.exiting and self._adapter_running:
                # Shutdown may arrive while a compensating reconnect itself
                # is awaiting IO. Retain ownership until it is disconnected.
                await self._sync_adapter(desired=False)

        async def change() -> tuple[bool, str]:
            if self._app is not None:
                return False, "运行中始终使用 OneBot 连接；请先进入待机再切换。"
            if not await self._sync_adapter(desired=bool(enabled)):
                return False, "切换 OneBot 连接失败（详见日志）；当前连接状态未改变。"
            return True, "待机期已保持 OneBot 连接。" if enabled else "待机期已断开 OneBot 连接。"

        return await self._perform(change, on_abort=compensate)

    def request_process_restart(self) -> bool:
        if self._restart_signal is not None:
            self._restart_signal.request()
            return True
        request = getattr(self._app, "request_restart", None)
        if not callable(request):
            return False
        request()
        return True

    async def _stop_runtime(self) -> None:
        app = self._app
        if app is None:
            return
        self._phase = "stopping"
        request = getattr(app, "request_stop", None)
        if callable(request):
            request()
        self._stopping_task = asyncio.create_task(app.stop(), name="neobot-runtime-stop")
        # 停机不上报超时：慢 ≠ 卡死，且这一代已被 request_stop 判死，没有「尽早失败」
        # 可救的东西。上报只会让服务把一次成功的软重启判成失败，并把状态退回待机。
        await self._wait_stage(self._stopping_task, STOP_TIMEOUT_SECONDS, prognostic=False)
        # Only successful completion relinquishes ownership. Failure retains app
        # for a subsequent explicit retry instead of publishing another runtime.
        self._app = None
        self._stopping_task = None
        self._adapter_running = False

    async def _dispose(self, app: Any) -> None:
        disposer = getattr(app, "dispose", app.stop)
        await disposer()

    async def _discard_initial(self) -> None:
        if self._initial is None:
            return
        self._phase = "startup_cleanup"
        task = asyncio.create_task(self._dispose(self._initial))
        await self._wait_stage(task, STOP_TIMEOUT_SECONDS)
        self._initial = None

    async def _start_runtime(self) -> None:
        if self.exiting or self._aborted:
            return
        # A failed rollback is retained too; it must be retried before assembly
        # mutates core host/registry bindings for a new generation.
        if self._starting_app is not None:
            self._phase = "startup_cleanup"
            task = asyncio.create_task(self._dispose(self._starting_app))
            await self._wait_stage(task, STOP_TIMEOUT_SECONDS)
            self._starting_app = None
            if self.exiting or self._aborted:
                return
        # Hand the standby connection back before runtime.start owns it. This
        # avoids a double start and, on early startup failure, an untracked core
        # adapter that rollback never reached and shutdown would otherwise miss.
        if self._adapter_running:
            await self._sync_adapter(desired=False)
            if self.exiting or self._aborted:
                return
        app = self._initial if self._initial is not None else self._factory()
        self._initial = None
        self._starting_app = app
        self._phase = "starting"
        self._starting_task = asyncio.create_task(app.start(), name="neobot-runtime-start")
        try:
            await self._wait_stage(self._starting_task, START_TIMEOUT_SECONDS)
            if not self.exiting and not self._aborted:
                self._app = app
                self._starting_app = None
                self._adapter_running = self._adapter is not None
                self._phase = "running"
                return
        except asyncio.CancelledError:
            # start() has completed rollback (possibly deferring cancellation).
            # Also dispose a start that was cancelled before it even entered.
            if not self._aborted and not self.exiting:
                raise
        finally:
            self._starting_task = None
            if self._starting_app is app:
                self._phase = "startup_cleanup"
                cleanup = asyncio.create_task(self._dispose(app), name="neobot-startup-cleanup")
                await self._wait_stage(cleanup, STOP_TIMEOUT_SECONDS)
                self._starting_app = None
                self._adapter_running = False

    async def _sync_adapter(self, *, desired: bool) -> bool:
        if self._adapter is None or desired == self._adapter_running:
            return True
        self._phase = "onebot_starting" if desired else "onebot_stopping"
        action = self._adapter.start if desired else self._adapter.stop
        task = asyncio.create_task(action())
        await self._wait_stage(task, STOP_TIMEOUT_SECONDS)
        self._adapter_running = desired
        return not self._aborted
