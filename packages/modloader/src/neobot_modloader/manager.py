from __future__ import annotations

import inspect
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
    error: Exception | None = None


class DefaultPluginManager:
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._records: dict[str, PluginRecord] = {}

    def register(self, plugin: Any, context: Any) -> None:
        name = context.plugin_name
        if name in self._records:
            raise ValueError(f"插件已注册: {name}")
        self._records[name] = PluginRecord(name=name, plugin=plugin, context=context)

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

    async def load_plugin(self, name: str) -> None:
        record = self._records[name]
        if record.state not in {PluginState.UNLOADED, PluginState.STOPPED}:
            return
        try:
            await self._maybe_await(record.plugin.on_load(record.context))
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件加载失败 ({name}): {exc}")
            self._unsubscribe_all(record)
            await self._cleanup_agents(record)
            return
        record.state = PluginState.LOADED
        record.error = None

    async def start_plugin(self, name: str) -> None:
        record = self._records[name]
        if record.state is PluginState.STOPPED:
            await self.load_plugin(name)
        if record.state is not PluginState.LOADED:
            return
        try:
            await self._maybe_await(record.plugin.on_start())
        except Exception as exc:
            record.error = exc
            record.state = PluginState.ERROR
            self._logger.exception(f"插件启动失败 ({name}): {exc}")
            self._unsubscribe_all(record)
            await self._cleanup_agents(record)
            return
        record.state = PluginState.RUNNING
        record.error = None

    async def stop_plugin(self, name: str) -> None:
        record = self._records[name]
        if record.state in {PluginState.UNLOADED, PluginState.STOPPED}:
            return
        should_mark_stopped = record.state is not PluginState.ERROR
        if record.state in {PluginState.LOADED, PluginState.RUNNING}:
            try:
                await self._maybe_await(record.plugin.on_stop())
            except Exception as exc:
                record.error = exc
                self._logger.exception(f"插件停止失败 ({name}): {exc}")
        self._unsubscribe_all(record)
        await self._cleanup_agents(record)
        if should_mark_stopped:
            record.state = PluginState.STOPPED

    async def load_all(self) -> None:
        for name in list(self._records):
            await self.load_plugin(name)

    async def start_all(self) -> None:
        for name in list(self._records):
            await self.start_plugin(name)

    async def stop_all(self) -> None:
        for name in reversed(list(self._records)):
            await self.stop_plugin(name)

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _unsubscribe_all(self, record: PluginRecord) -> None:
        subscriptions = record.subscriptions
        record.subscriptions = []
        for subscription in subscriptions:
            try:
                subscription.unsubscribe()
            except Exception as exc:
                self._logger.exception(f"插件订阅清理失败 ({record.name}): {exc}")

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
