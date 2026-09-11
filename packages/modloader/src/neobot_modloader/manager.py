from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.dependency import (
    PluginDependencyError,
    parse_dependencies,
    version_satisfies,
)

#: 前置插件处于这些状态才允许被依赖方调用
_READY_STATES = frozenset({PluginState.LOADED, PluginState.RUNNING})


class ReentrantLock:
    """按任务可重入的 asyncio 锁。

    同一任务可嵌套获取（回调内经 plugin_control 重新进入同名操作不会自死锁）；
    不同任务仍排队串行。``_pending`` 记录排队获取者，供运行时的闲置剪枝判断。
    """

    __slots__ = ("_lock", "_owner", "_depth", "_pending")

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0
        self._pending = 0

    async def __aenter__(self) -> "ReentrantLock":
        await self.acquire()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.release()

    async def acquire(self) -> None:
        task = asyncio.current_task()
        if self._owner is task and self._depth > 0:
            self._depth += 1
            return
        self._pending += 1
        try:
            await self._lock.acquire()
            self._owner = task
            self._depth = 1
        finally:
            self._pending -= 1

    def release(self) -> None:
        if self._owner is not asyncio.current_task():
            raise RuntimeError("lock released by a different task")
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()

    def is_owned_by_current_task(self) -> bool:
        return self._owner is asyncio.current_task()

    def held_by_other_task(self) -> bool:
        owner = self._owner
        return owner is not None and owner is not asyncio.current_task()

    def in_use(self) -> bool:
        return self._owner is not None or self._pending > 0

    def is_free(self) -> bool:
        return not self.in_use()


@dataclass(slots=True)
class PluginRecord:
    name: str
    plugin: Any
    context: Any
    state: PluginState = PluginState.UNLOADED
    subscriptions: list[Any] = field(default_factory=list)
    agent_registrations: list[tuple[str, Any]] = field(default_factory=list)
    cleanup_callbacks: list[Any] = field(default_factory=list)
    error: Exception | None = None
    stop_failed: bool = False
    _teardown_depth: int = field(default=0, repr=False)
    _agent_close_pending: set[int] = field(default_factory=set, repr=False)


class PluginHandle:
    def __init__(self, manager: DefaultPluginManager, name: str) -> None:
        self._manager = manager
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        record = self._record()
        return str(getattr(record.plugin, "version", ""))

    @property
    def state(self) -> PluginState:
        return self._manager.get_state(self._name)

    @property
    def dependencies(self) -> tuple[str, ...]:
        """本插件声明的依赖（原始声明文本，可能带版本约束）。"""
        return tuple(str(item) for item in (getattr(self._record().plugin, "dependencies", ()) or ()))

    @property
    def ready(self) -> bool:
        """前置插件是否处于可调用状态（已加载或运行中）。"""
        return self._record().state in _READY_STATES

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(_capability_names(self._record().plugin))

    def satisfies(self, specifier: str = "") -> bool | None:
        """本插件版本是否满足约束串（None 表示无法比较）。"""
        if not specifier:
            return True
        return version_satisfies(self.version, specifier)

    def require(self, specifier: str = "") -> "PluginHandle":
        """校验本插件已就绪且版本满足约束，否则抛 PluginDependencyError。"""
        if not self.ready:
            raise PluginDependencyError(
                f"前置插件未就绪: {self._name}（当前状态: {self.state.value}）"
            )
        verdict = self.satisfies(specifier)
        if verdict is False:
            raise PluginDependencyError(
                f"前置插件版本不满足: 需要 {self._name}{specifier}，当前 {self.version}"
            )
        return self

    async def call(
        self, capability: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        record = self._record()
        payload_dict = dict(payload or {})
        names = set(_capability_names(record.plugin))
        if capability not in names:
            raise KeyError(f"插件 {self._name!r} 未导出能力 {capability!r}")

        call_capability = getattr(record.plugin, "call_capability", None)
        if callable(call_capability):
            return await _maybe_await(call_capability(capability, payload_dict))

        invoke_capability = getattr(record.plugin, "invoke_capability", None)
        if callable(invoke_capability):
            return await _maybe_await(invoke_capability(capability, payload_dict))

        capabilities = getattr(record.plugin, "capabilities", None)
        if callable(capabilities):
            capabilities = capabilities()
        if isinstance(capabilities, Mapping):
            target = capabilities[capability]
            if callable(target):
                return await _maybe_await(target(payload_dict))
            call = getattr(target, "call", None)
            if callable(call):
                return await _maybe_await(call(payload_dict))
            invoke = getattr(target, "invoke", None)
            if callable(invoke):
                return await _maybe_await(invoke(payload_dict))

        raise RuntimeError(f"插件 {self._name!r} 的能力 {capability!r} 不可调用")

    def _record(self) -> PluginRecord:
        record = self._manager.get_record(self._name)
        if record is None:
            raise KeyError(f"插件未注册: {self._name}")
        return record


class PluginRegistryView:
    def __init__(self, manager: DefaultPluginManager) -> None:
        self._manager = manager

    def names(self) -> list[str]:
        return self._manager.names()

    def has(self, name: str) -> bool:
        return self._manager.get_record(name) is not None

    def get(self, name: str) -> PluginHandle | None:
        if not self.has(name):
            return None
        return PluginHandle(self._manager, name)

    def list(self) -> list[PluginHandle]:
        return [PluginHandle(self._manager, name) for name in self.names()]

    def require(self, name: str, specifier: str = "") -> PluginHandle:
        """取得前置插件句柄并校验就绪状态与版本。

        插件里调用前置插件的功能一律走这里::

            handle = ctx.plugins.require("dashboard", ">=1.0.0")
            await handle.call("web.register_extension", {"extension": ext})

        前置插件不存在 / 未就绪 / 版本不满足都会抛出 PluginDependencyError，
        错误文本可直接展示给用户。
        """
        if not self.has(name):
            raise PluginDependencyError(f"前置插件未加载: {name}")
        return PluginHandle(self._manager, name).require(specifier)

    def optional(self, name: str) -> PluginHandle | None:
        """取得可选的前置插件句柄；不存在或未就绪时返回 None。"""
        if not self.has(name):
            return None
        handle = PluginHandle(self._manager, name)
        return handle if handle.ready else None

    def dependents_of(self, name: str, *, transitive: bool = False) -> list[str]:
        """返回依赖指定插件的插件名（transitive=True 时递归整条依赖链）。"""
        direct: list[str] = []
        for candidate in self.names():
            if candidate == name:
                continue
            if name in _declared_dependency_names(self._manager, candidate):
                direct.append(candidate)
        if not transitive:
            return direct
        collected: list[str] = []
        pending = list(direct)
        while pending:
            current = pending.pop()
            if current in collected:
                continue
            collected.append(current)
            pending.extend(self.dependents_of(current))
        return collected

    def dependency_issues(self, name: str) -> list[str]:
        """指定插件当前未满足的依赖（缺失 / 未就绪 / 版本不符）。"""
        issues: list[str] = []
        if not self.has(name):
            return [f"插件未加载: {name}"]
        for dependency in _declared_dependencies(self._manager, name):
            handle = self.get(dependency.name)
            if handle is None:
                issues.append(f"缺少前置插件: {dependency.describe()}")
                continue
            if not handle.ready:
                issues.append(
                    f"前置插件未就绪: {dependency.describe()}（{handle.state.value}）"
                )
                continue
            if dependency.matches(handle.version) is False:
                issues.append(
                    f"前置插件版本不满足: {dependency.describe()}，当前 {handle.version}"
                )
        return issues


class DefaultPluginManager:
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._records: dict[str, PluginRecord] = {}
        self._registry_view = PluginRegistryView(self)
        self._lock = asyncio.Lock()
        self._plugin_locks: dict[str, ReentrantLock] = {}

    @property
    def registry_view(self) -> PluginRegistryView:
        return self._registry_view

    def names(self) -> list[str]:
        return list(self._records)

    def get_record(self, name: str) -> PluginRecord | None:
        return self._records.get(name)

    def register(self, plugin: Any, context: Any) -> None:
        name = context.plugin_name
        if name in self._records:
            raise ValueError(f"插件已注册: {name}")
        self._records[name] = PluginRecord(name=name, plugin=plugin, context=context)
        # Locks are intentionally permanent per name. Replacing one lets an operation
        # queued on the old lock race a newly registered record.
        self._plugin_locks.setdefault(name, ReentrantLock())

    def get_plugin(self, name: str) -> Any | None:
        record = self._records.get(name)
        return record.plugin if record is not None else None

    async def remove_plugin(
        self,
        name: str,
        *,
        expected: PluginRecord | None = None,
        force: bool = False,
    ) -> PluginRecord | None:
        record = self._records.get(name) if expected is None else expected
        if record is None:
            return None
        lock = self._plugin_locks.get(name)
        if lock is None:
            return None
        async with lock:
            if self._records.get(name) is not record:
                return None
            if force:
                try:
                    await self._stop_plugin_locked(record)
                finally:
                    if self._records.get(name) is record:
                        self._records.pop(name)
                current = self._records.get(name)
                return record if current is None else None

            teardown_ok = await self._stop_plugin_locked(record)
            if not teardown_ok:
                return record
            if self._records.get(name) is not record:
                return record if self._records.get(name) is None else None
            self._records.pop(name)
            return record

    def get_state(self, name: str) -> PluginState:
        record = self._records.get(name)
        return record.state if record is not None else PluginState.UNLOADED

    def get_subscriptions(self, name: str) -> list[Any]:
        record = self._records.get(name)
        if record is None:
            return []
        return list(record.subscriptions)

    def record_subscription(self, name: str, subscription: Any) -> None:
        record = self._record_for_resource(name)
        record.subscriptions.append(subscription)

    def record_agent_registration(
        self, name: str, registered_name: str, agent: Any
    ) -> None:
        record = self._record_for_resource(name)
        record.agent_registrations.append((registered_name, agent))

    def record_cleanup(self, name: str, cleanup: Any) -> None:
        record = self._record_for_resource(name)
        record.cleanup_callbacks.append(cleanup)

    def _record_for_resource(self, name: str) -> PluginRecord:
        record = self._records.get(name)
        if record is None:
            raise KeyError(f"插件未注册: {name}")
        if record._teardown_depth or record.state in {
            PluginState.STOPPING,
            PluginState.STOPPED,
            PluginState.ERROR,
        }:
            raise RuntimeError(f"插件正在停止或已停止，不能再登记资源: {name}")
        return record

    async def load_plugin(self, name: str) -> None:
        record = self._records.get(name)
        if record is None:
            return
        lock = self._plugin_locks[name]
        async with lock:
            if self._records.get(name) is record:
                await self._load_plugin_locked(record)

    async def _load_plugin_locked(self, record: PluginRecord) -> None:
        name = record.name
        if record.state not in {PluginState.UNLOADED, PluginState.STOPPED}:
            return
        if record.state is PluginState.STOPPED:
            cleanup_errors = await self._teardown_owned_resources(record)
            if cleanup_errors:
                record.error = _error_from("插件清理失败", cleanup_errors)
                return
            record.error = None
        try:
            self._set_state(record, "LOADING")
            await self._maybe_await(record.plugin.on_load(record.context))
        except asyncio.CancelledError:
            # 取消不得留下 LOADING 僵尸纪录：进入终态、清理资源后重新抛出
            record.state = PluginState.ERROR
            record.error = RuntimeError(f"插件加载被取消 ({name})")
            cleanup_errors = await self._teardown_owned_resources(record)
            if cleanup_errors:
                record.error = _error_from(
                    "插件加载取消及回滚失败", [record.error, *cleanup_errors]
                )
            raise
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件加载失败 ({name}): {exc}")
            cleanup_errors = await self._teardown_owned_resources(record)
            if cleanup_errors:
                record.error = _error_from("插件加载及回滚失败", [exc, *cleanup_errors])
            return
        if self._records.get(name) is record and record.state is PluginState.LOADING:
            record.state = PluginState.LOADED
            record.error = None
            record.stop_failed = False

    async def start_plugin(self, name: str) -> None:
        record = self._records.get(name)
        if record is None:
            return
        lock = self._plugin_locks[name]
        async with lock:
            if self._records.get(name) is record:
                await self._start_plugin_locked(record)

    async def _start_plugin_locked(self, record: PluginRecord) -> None:
        name = record.name
        if record.state is PluginState.STOPPED:
            await self._load_plugin_locked(record)
        if record.state is not PluginState.LOADED:
            return
        try:
            self._set_state(record, "STARTING")
            await self._maybe_await(record.plugin.on_start())
        except asyncio.CancelledError:
            record.state = PluginState.ERROR
            record.error = RuntimeError(f"插件启动被取消 ({name})")
            cleanup_errors = await self._teardown_owned_resources(record)
            if cleanup_errors:
                record.error = _error_from(
                    "插件启动取消及回滚失败", [record.error, *cleanup_errors]
                )
            raise
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件启动失败 ({name}): {exc}")
            cleanup_errors = await self._teardown_owned_resources(record)
            if cleanup_errors:
                record.error = _error_from("插件启动及回滚失败", [exc, *cleanup_errors])
            return
        if self._records.get(name) is record and record.state is PluginState.STARTING:
            record.state = PluginState.RUNNING
            record.error = None

    async def stop_plugin(self, name: str) -> None:
        record = self._records.get(name)
        if record is None:
            return
        lock = self._plugin_locks[name]
        async with lock:
            if self._records.get(name) is record:
                await self._stop_plugin_locked(record)

    async def _stop_plugin_locked(self, record: PluginRecord) -> bool:
        name = record.name
        if record.state is PluginState.STOPPING or record._teardown_depth:
            # The active outer stop owns final state/error bookkeeping. A same-task
            # remove must report incomplete without poisoning a stop that may succeed.
            return False

        initial_state = record.state
        terminal_state = (
            PluginState.ERROR
            if initial_state is PluginState.ERROR
            else PluginState.STOPPED
        )
        persistent_error = record.error if initial_state is PluginState.ERROR else None
        if initial_state is PluginState.ERROR and persistent_error is None:
            persistent_error = RuntimeError(f"插件处于错误状态但没有错误信息: {name}")
        recoverable_error = (
            record.error if initial_state is not PluginState.ERROR else None
        )
        errors: list[Exception] = (
            [persistent_error] if persistent_error is not None else []
        )
        cancellation: asyncio.CancelledError | None = None
        callback_needed = initial_state in {
            PluginState.LOADED,
            PluginState.RUNNING,
        } or (initial_state is PluginState.STOPPED and record.stop_failed)

        try:
            if callback_needed:
                callback_error_before = record.error
                callback_failed = False
                cancellation_baseline = _cancellation_count()
                self._set_state(record, "STOPPING")
                try:
                    await self._maybe_await(record.plugin.on_stop())
                except asyncio.CancelledError as exc:
                    callback_failed = True
                    errors.append(_cancelled_failure(f"插件停止被取消 ({name})", exc))
                    if _cancellation_requested_since(cancellation_baseline):
                        cancellation = exc
                    else:
                        self._logger.exception(f"插件停止回调取消失败 ({name}): {exc}")
                except Exception as exc:
                    callback_failed = True
                    errors.append(exc)
                    self._logger.exception(f"插件停止失败 ({name}): {exc}")
                finally:
                    callback_side_error = record.error
                    if (
                        callback_side_error is not None
                        and callback_side_error is not callback_error_before
                    ):
                        _append_error_once(errors, callback_side_error)
                    elif callback_failed and callback_error_before is not None:
                        _append_error_once(errors, callback_error_before)
                    record.stop_failed = callback_failed
                    record.state = terminal_state
                    record.error = (
                        _error_from("插件停止失败", errors) if errors else None
                    )
            else:
                record.state = terminal_state
                if persistent_error is not None:
                    record.error = persistent_error

            cleanup_errors: list[Exception] = []
            cleanup_cancellation_baseline = _cancellation_count()
            try:
                await self._teardown_owned_resources(
                    record,
                    errors=cleanup_errors,
                    cancellation_baseline=cleanup_cancellation_baseline,
                )
            except asyncio.CancelledError as exc:
                if not any(error.__cause__ is exc for error in cleanup_errors):
                    cleanup_errors.append(
                        _cancelled_failure(f"插件资源清理被取消 ({name})", exc)
                    )
                if cancellation is None:
                    cancellation = exc

            if cleanup_errors:
                if (
                    not callback_needed
                    and persistent_error is None
                    and recoverable_error is not None
                ):
                    _append_error_once(errors, recoverable_error)
                errors.extend(cleanup_errors)
        finally:
            record.state = terminal_state
            record.error = _error_from("插件停止失败", errors) if errors else None

        if cancellation is not None:
            raise cancellation
        return not errors

    async def load_all(self) -> None:
        async with self._lock:
            for name in list(self._records):
                await self.load_plugin(name)

    async def start_all(self) -> None:
        async with self._lock:
            for name in list(self._records):
                await self.start_plugin(name)

    async def stop_all(self) -> None:
        async with self._lock:
            for name in reversed(list(self._records)):
                await self.stop_plugin(name)

    async def _maybe_await(self, value: Any) -> Any:
        return await _maybe_await(value)

    def _set_state(self, record: PluginRecord, state: PluginState | str) -> None:
        if isinstance(state, PluginState):
            record.state = state
            return
        next_state = getattr(PluginState, state, None)
        if isinstance(next_state, PluginState):
            record.state = next_state

    async def _teardown_owned_resources(
        self,
        record: PluginRecord,
        *,
        errors: list[Exception] | None = None,
        cancellation_baseline: int | None = None,
    ) -> list[Exception]:
        collected = [] if errors is None else errors
        baseline = (
            _cancellation_count()
            if cancellation_baseline is None
            else cancellation_baseline
        )
        record._teardown_depth += 1
        try:
            self._cleanup_callbacks(record, collected, baseline)
            self._unsubscribe_all(record, collected, baseline)
            await self._cleanup_agents(record, collected, baseline)
            await self._close_plugin_databases(record, collected, baseline)
        finally:
            record._teardown_depth -= 1
        return collected

    async def _close_plugin_databases(
        self,
        record: PluginRecord,
        errors: list[Exception],
        cancellation_baseline: int,
    ) -> None:
        """关闭插件声明的数据库引擎。

        on_stop 是唯一的关闭入口，而插件处于 ERROR 状态时 _stop_plugin_locked
        会跳过 on_stop（callback_needed 只认 LOADED/RUNNING）：声明了数据库的
        插件若在 on_load/on_start 阶段失败，引擎会一直挂着，Windows 上持续
        锁住插件数据库文件。这里纳入统一的 teardown，覆盖全部失败路径。
        """
        close_databases = getattr(record.plugin, "close_databases", None)
        if not callable(close_databases):
            return
        try:
            await self._maybe_await(close_databases())
        except asyncio.CancelledError as exc:
            error = _cancelled_failure(f"插件数据库关闭被取消 ({record.name})", exc)
            errors.append(error)
            self._logger.exception(f"插件数据库关闭失败 ({record.name}): {exc}")
            if _cancellation_requested_since(cancellation_baseline):
                raise
        except Exception as exc:
            errors.append(exc)
            self._logger.exception(f"插件数据库关闭失败 ({record.name}): {exc}")

    def _unsubscribe_all(
        self,
        record: PluginRecord,
        errors: list[Exception],
        cancellation_baseline: int,
    ) -> None:
        for subscription in list(record.subscriptions):
            try:
                subscription.unsubscribe()
            except asyncio.CancelledError as exc:
                error = _cancelled_failure(f"插件订阅清理被取消 ({record.name})", exc)
                errors.append(error)
                self._logger.exception(f"插件订阅清理失败 ({record.name}): {exc}")
                if _cancellation_requested_since(cancellation_baseline):
                    raise
            except Exception as exc:
                errors.append(exc)
                self._logger.exception(f"插件订阅清理失败 ({record.name}): {exc}")
            else:
                _remove_identity(record.subscriptions, subscription)

    def _cleanup_callbacks(
        self,
        record: PluginRecord,
        errors: list[Exception],
        cancellation_baseline: int,
    ) -> None:
        for cleanup in reversed(list(record.cleanup_callbacks)):
            try:
                cleanup()
            except asyncio.CancelledError as exc:
                error = _cancelled_failure(f"插件资源清理被取消 ({record.name})", exc)
                errors.append(error)
                self._logger.exception(f"插件资源清理失败 ({record.name}): {exc}")
                if _cancellation_requested_since(cancellation_baseline):
                    raise
            except Exception as exc:
                errors.append(exc)
                self._logger.exception(f"插件资源清理失败 ({record.name}): {exc}")
            else:
                _remove_last_identity(record.cleanup_callbacks, cleanup)

    async def _cleanup_agents(
        self,
        record: PluginRecord,
        errors: list[Exception],
        cancellation_baseline: int,
    ) -> None:
        registrar = getattr(record.context, "agents", None)
        for registration in list(record.agent_registrations):
            registered_name, agent = registration
            # 优先走支持在途委托排空的 unregister_and_drain（由注册表负责注销、
            # 取消在途任务并关闭实例）；旧注册表回退 unregister + close 组合
            unregister_and_drain = getattr(registrar, "unregister_and_drain", None)
            if callable(unregister_and_drain):
                try:
                    await self._maybe_await(unregister_and_drain(registered_name))
                except asyncio.CancelledError as exc:
                    error = _cancelled_failure(
                        f"插件 Agent 注销被取消 ({record.name}/{registered_name})", exc
                    )
                    errors.append(error)
                    self._logger.exception(
                        f"插件 Agent 注销失败 ({record.name}/{registered_name}): {exc}"
                    )
                    if _cancellation_requested_since(cancellation_baseline):
                        raise
                except Exception as exc:
                    errors.append(exc)
                    self._logger.exception(
                        f"插件 Agent 注销失败 ({record.name}/{registered_name}): {exc}"
                    )
                else:
                    _remove_identity(record.agent_registrations, registration)
                continue

            registration_id = id(registration)
            if registration_id not in record._agent_close_pending:
                try:
                    unregister = getattr(registrar, "unregister", None)
                    if callable(unregister):
                        await self._maybe_await(unregister(registered_name))
                except asyncio.CancelledError as exc:
                    error = _cancelled_failure(
                        f"插件 Agent 注销被取消 ({record.name}/{registered_name})", exc
                    )
                    errors.append(error)
                    self._logger.exception(
                        f"插件 Agent 注销失败 ({record.name}/{registered_name}): {exc}"
                    )
                    if _cancellation_requested_since(cancellation_baseline):
                        raise
                    continue
                except Exception as exc:
                    errors.append(exc)
                    self._logger.exception(
                        f"插件 Agent 注销失败 ({record.name}/{registered_name}): {exc}"
                    )
                    continue
                record._agent_close_pending.add(registration_id)

            try:
                close = getattr(agent, "close", None)
                if callable(close):
                    await self._maybe_await(close())
            except asyncio.CancelledError as exc:
                error = _cancelled_failure(
                    f"插件 Agent 关闭被取消 ({record.name}/{registered_name})", exc
                )
                errors.append(error)
                self._logger.exception(
                    f"插件 Agent 关闭失败 ({record.name}/{registered_name}): {exc}"
                )
                if _cancellation_requested_since(cancellation_baseline):
                    raise
            except Exception as exc:
                errors.append(exc)
                self._logger.exception(
                    f"插件 Agent 关闭失败 ({record.name}/{registered_name}): {exc}"
                )
            else:
                _remove_identity(record.agent_registrations, registration)
                record._agent_close_pending.discard(registration_id)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _error_from(message: str, errors: list[Exception]) -> Exception:
    if len(errors) == 1:
        return errors[0]
    details = "; ".join(filter(None, (_error_details(error) for error in errors)))
    group_message = f"{message}: {details}" if details else message
    return ExceptionGroup(group_message, errors)


def _error_details(error: Exception) -> str:
    if isinstance(error, ExceptionGroup):
        return "; ".join(
            filter(None, (_error_details(nested) for nested in error.exceptions))
        )
    return str(error)


def _append_error_once(errors: list[Exception], error: Exception) -> None:
    if all(existing is not error for existing in errors):
        errors.append(error)


def _cancellation_count() -> int:
    task = asyncio.current_task()
    return task.cancelling() if task is not None else 0


def _cancellation_requested_since(baseline: int) -> bool:
    return _cancellation_count() > baseline


def _cancelled_failure(
    message: str, cancellation: asyncio.CancelledError
) -> RuntimeError:
    error = RuntimeError(message)
    error.__cause__ = cancellation
    return error


def _remove_identity(items: list[Any], target: Any) -> None:
    for index, item in enumerate(items):
        if item is target:
            items.pop(index)
            return


def _remove_last_identity(items: list[Any], target: Any) -> None:
    for index in range(len(items) - 1, -1, -1):
        if items[index] is target:
            items.pop(index)
            return


def _declared_dependencies(
    manager: DefaultPluginManager, name: str
) -> list[Any]:
    """解析某个插件声明的依赖；声明非法时按「无依赖」处理（不阻塞依赖链计算）。"""
    record = manager.get_record(name)
    if record is None:
        return []
    raw = getattr(record.plugin, "dependencies", ()) or ()
    try:
        return list(parse_dependencies(raw))
    except (TypeError, ValueError):
        return []


def _declared_dependency_names(manager: DefaultPluginManager, name: str) -> set[str]:
    return {dependency.name for dependency in _declared_dependencies(manager, name)}


def _capability_names(plugin: Any) -> list[str]:
    capabilities = getattr(plugin, "capabilities", None)
    if callable(capabilities):
        try:
            capabilities = capabilities()
        except TypeError:
            pass
    if isinstance(capabilities, Mapping):
        return [str(name) for name in capabilities]
    if capabilities is None:
        return []
    names: list[str] = []
    for item in capabilities:
        name = getattr(item, "name", item)
        if name is not None:
            names.append(str(name))
    return names
