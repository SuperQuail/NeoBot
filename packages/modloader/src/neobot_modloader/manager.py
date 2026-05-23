from __future__ import annotations

import inspect
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.plugin import PluginState


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
    def capabilities(self) -> tuple[str, ...]:
        return tuple(_capability_names(self._record().plugin))

    async def call(self, capability: str, payload: Mapping[str, Any] | None = None) -> Any:
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


class DefaultPluginManager:
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._records: dict[str, PluginRecord] = {}
        self._registry_view = PluginRegistryView(self)
        self._lock = asyncio.Lock()
        self._plugin_locks: dict[str, asyncio.Lock] = {}

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
        self._plugin_locks[name] = asyncio.Lock()

    def get_plugin(self, name: str) -> Any | None:
        record = self._records.get(name)
        return record.plugin if record is not None else None

    def get_state(self, name: str) -> PluginState:
        record = self._records.get(name)
        return record.state if record is not None else PluginState.UNLOADED

    def get_subscriptions(self, name: str) -> list[Any]:
        record = self._records.get(name)
        if record is None:
            return []
        return list(record.subscriptions)

    def record_subscription(self, name: str, subscription: Any) -> None:
        record = self._records.get(name)
        if record is None:
            raise KeyError(f"插件未注册: {name}")
        record.subscriptions.append(subscription)

    def record_agent_registration(self, name: str, registered_name: str, agent: Any) -> None:
        record = self._records.get(name)
        if record is None:
            raise KeyError(f"插件未注册: {name}")
        record.agent_registrations.append((registered_name, agent))

    def record_cleanup(self, name: str, cleanup: Any) -> None:
        record = self._records.get(name)
        if record is None:
            raise KeyError(f"插件未注册: {name}")
        record.cleanup_callbacks.append(cleanup)

    async def load_plugin(self, name: str) -> None:
        async with self._plugin_locks[name]:
            await self._load_plugin_locked(name)

    async def _load_plugin_locked(self, name: str) -> None:
        record = self._records[name]
        if record.state not in {PluginState.UNLOADED, PluginState.STOPPED}:
            return
        try:
            self._set_state(record, "LOADING")
            await self._maybe_await(record.plugin.on_load(record.context))
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件加载失败 ({name}): {exc}")
            self._cleanup_callbacks(record)
            self._unsubscribe_all(record)
            await self._cleanup_agents(record)
            return
        record.state = PluginState.LOADED
        record.error = None

    async def start_plugin(self, name: str) -> None:
        async with self._plugin_locks[name]:
            await self._start_plugin_locked(name)

    async def _start_plugin_locked(self, name: str) -> None:
        record = self._records[name]
        if record.state is PluginState.STOPPED:
            await self._load_plugin_locked(name)
        if record.state is not PluginState.LOADED:
            return
        try:
            self._set_state(record, "STARTING")
            await self._maybe_await(record.plugin.on_start())
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件启动失败 ({name}): {exc}")
            self._cleanup_callbacks(record)
            self._unsubscribe_all(record)
            await self._cleanup_agents(record)
            return
        record.state = PluginState.RUNNING
        record.error = None

    async def stop_plugin(self, name: str) -> None:
        async with self._plugin_locks[name]:
            await self._stop_plugin_locked(name)

    async def _stop_plugin_locked(self, name: str) -> None:
        record = self._records[name]
        if record.state in {PluginState.UNLOADED, PluginState.STOPPED}:
            return
        should_mark_stopped = record.state is not PluginState.ERROR
        if record.state in {PluginState.LOADED, PluginState.RUNNING}:
            try:
                self._set_state(record, "STOPPING")
                await self._maybe_await(record.plugin.on_stop())
            except Exception as exc:
                record.error = exc
                self._logger.exception(f"插件停止失败 ({name}): {exc}")
        self._cleanup_callbacks(record)
        self._unsubscribe_all(record)
        await self._cleanup_agents(record)
        if should_mark_stopped:
            record.state = PluginState.STOPPED

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

    def _unsubscribe_all(self, record: PluginRecord) -> None:
        subscriptions = record.subscriptions
        record.subscriptions = []
        for subscription in subscriptions:
            try:
                subscription.unsubscribe()
            except Exception as exc:
                self._logger.exception(f"插件订阅清理失败 ({record.name}): {exc}")

    def _cleanup_callbacks(self, record: PluginRecord) -> None:
        callbacks = record.cleanup_callbacks
        record.cleanup_callbacks = []
        for cleanup in reversed(callbacks):
            try:
                cleanup()
            except Exception as exc:
                self._logger.exception(f"插件资源清理失败 ({record.name}): {exc}")

    async def _cleanup_agents(self, record: PluginRecord) -> None:
        registrations = record.agent_registrations
        record.agent_registrations = []
        registrar = getattr(record.context, "agents", None)
        for registered_name, agent in registrations:
            try:
                unregister = getattr(registrar, "unregister", None)
                if callable(unregister):
                    unregister(registered_name)
            except Exception as exc:
                self._logger.exception(f"插件 Agent 注销失败 ({record.name}/{registered_name}): {exc}")
            try:
                close = getattr(agent, "close", None)
                if callable(close):
                    await self._maybe_await(close())
            except Exception as exc:
                self._logger.exception(f"插件 Agent 关闭失败 ({record.name}/{registered_name}): {exc}")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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
