"""Concrete host facade and registries for modloader/runtime."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.runtime_event import RuntimeEnvelope, RuntimeInterceptionRegistry


# ---------------------------------------------------------------------------
# Generic registry helper
# ---------------------------------------------------------------------------


class _Registry:
    def __init__(self, label: str) -> None:
        self._label = label
        self._entries: dict[str, Any] = {}

    def names(self) -> list[str]:
        return list(self._entries)

    def get(self, name: str) -> Any | None:
        return self._entries.get(name)


# ---------------------------------------------------------------------------
# CommandRegistry — 统一写操作
# ---------------------------------------------------------------------------


class DefaultCommandRegistry(_Registry):
    def __init__(self) -> None:
        super().__init__("command")

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        schema: dict[str, Any] | None = None,
        override: bool = False,
    ) -> None:
        if name in self._entries and not override:
            raise ValueError(f"命令已注册: {name!r}")
        self._entries[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "schema": schema or {},
        }

    def unregister(self, name: str) -> bool:
        return self._entries.pop(name, None) is not None

    async def call(self, name: str, **kwargs: Any) -> Any:
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"未知命令: {name!r}")
        return await _call(entry["handler"], **kwargs)


# ---------------------------------------------------------------------------
# QueryRegistry — 统一只读查询
# ---------------------------------------------------------------------------


class DefaultQueryRegistry(_Registry):
    def __init__(self) -> None:
        super().__init__("query")

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        schema: dict[str, Any] | None = None,
        override: bool = False,
    ) -> None:
        if name in self._entries and not override:
            raise ValueError(f"查询已注册: {name!r}")
        self._entries[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "schema": schema or {},
        }

    def unregister(self, name: str) -> bool:
        return self._entries.pop(name, None) is not None

    async def query(self, name: str, **kwargs: Any) -> Any:
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"未知查询: {name!r}")
        return await _call(entry["handler"], **kwargs)


# ---------------------------------------------------------------------------
# CapabilityRegistry — 统一能力注册与调用
# ---------------------------------------------------------------------------


class DefaultCapabilityRegistry(_Registry):
    def __init__(self) -> None:
        super().__init__("capability")

    def register(self, name: str, description: str, handler: Callable[..., Any], *, override: bool = False) -> None:
        if name in self._entries and not override:
            raise ValueError(f"能力已注册: {name!r}")
        self._entries[name] = {
            "name": name,
            "description": description,
            "handler": handler,
        }

    def unregister(self, name: str) -> bool:
        return self._entries.pop(name, None) is not None

    def list(self) -> list[Any]:
        return [
            {"name": name, "description": entry["description"]}
            for name, entry in self._entries.items()
        ]

    async def call(self, name: str, **kwargs: Any) -> Any:
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"未知能力: {name!r}")
        return await _call(entry["handler"], **kwargs)


# ---------------------------------------------------------------------------
# LifecycleHooks — 生命周期钩子
# ---------------------------------------------------------------------------


class DefaultLifecycleHooks:
    def __init__(self) -> None:
        self._stages: dict[str, list[tuple[int, Callable[..., Any]]]] = {}

    async def fire(self, stage: str, **kwargs: Any) -> Any:
        handlers = self._stages.get(stage, [])
        handlers.sort(key=lambda item: item[0], reverse=True)
        for _priority, handler in handlers:
            await _call(handler, stage=stage, **kwargs)

    def subscribe(self, stage: str, handler: Callable[..., Any], *, priority: int = 0) -> Callable[[], None]:
        self._stages.setdefault(stage, []).append((priority, handler))

        def _unsub() -> None:
            items = self._stages.get(stage, [])
            self._stages[stage] = [(p, h) for p, h in items if h is not handler]

        return _unsub


class TrackedPluginHostFacade:
    """Plugin-scoped host facade that records registrations for cleanup."""

    def __init__(self, host: "PluginHostFacade", record_cleanup: Callable[[Callable[[], None]], None]) -> None:
        self._host = host
        self._record_cleanup = record_cleanup
        self._commands = _TrackedCommandRegistry(host.commands, record_cleanup)
        self._queries = _TrackedQueryRegistry(host.queries, record_cleanup)
        self._capabilities = _TrackedCapabilityRegistry(host.capabilities, record_cleanup)
        self._lifecycle = _TrackedLifecycleHooks(host.lifecycle, record_cleanup)

    @property
    def events(self) -> RuntimeInterceptionRegistry:
        return self._host.events

    @property
    def output(self) -> OutputPort:
        return self._host.output

    @property
    def commands(self) -> "_TrackedCommandRegistry":
        return self._commands

    @property
    def queries(self) -> "_TrackedQueryRegistry":
        return self._queries

    @property
    def capabilities(self) -> "_TrackedCapabilityRegistry":
        return self._capabilities

    @property
    def lifecycle(self) -> "_TrackedLifecycleHooks":
        return self._lifecycle

    def register_skill(self, skill: Any) -> None:
        """注册 Skill，插件卸载时自动注销。"""
        self._host.register_skill(skill)
        self._record_cleanup(lambda name=skill.name: self._unregister_skill(name))

    def _unregister_skill(self, name: str) -> None:
        self._host._skills.unregister(name)


class _TrackedCommandRegistry:
    def __init__(self, registry: DefaultCommandRegistry, record_cleanup: Callable[[Callable[[], None]], None]) -> None:
        self._registry = registry
        self._record_cleanup = record_cleanup

    def names(self) -> list[str]:
        return self._registry.names()

    def get(self, name: str) -> Any | None:
        return self._registry.get(name)

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        schema: dict[str, Any] | None = None,
        override: bool = False,
    ) -> None:
        self._registry.register(name, description, handler, schema=schema, override=override)
        entry = self._registry.get(name)
        self._record_cleanup(lambda name=name, entry=entry: self._unregister_if_current(name, entry))

    def unregister(self, name: str) -> bool:
        return self._registry.unregister(name)

    async def call(self, name: str, **kwargs: Any) -> Any:
        return await self._registry.call(name, **kwargs)

    def _unregister_if_current(self, name: str, entry: Any) -> bool:
        if self._registry.get(name) is not entry:
            return False
        return self._registry.unregister(name)


class _TrackedQueryRegistry:
    def __init__(self, registry: DefaultQueryRegistry, record_cleanup: Callable[[Callable[[], None]], None]) -> None:
        self._registry = registry
        self._record_cleanup = record_cleanup

    def names(self) -> list[str]:
        return self._registry.names()

    def get(self, name: str) -> Any | None:
        return self._registry.get(name)

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        schema: dict[str, Any] | None = None,
        override: bool = False,
    ) -> None:
        self._registry.register(name, description, handler, schema=schema, override=override)
        entry = self._registry.get(name)
        self._record_cleanup(lambda name=name, entry=entry: self._unregister_if_current(name, entry))

    def unregister(self, name: str) -> bool:
        return self._registry.unregister(name)

    async def query(self, name: str, **kwargs: Any) -> Any:
        return await self._registry.query(name, **kwargs)

    def _unregister_if_current(self, name: str, entry: Any) -> bool:
        if self._registry.get(name) is not entry:
            return False
        return self._registry.unregister(name)


class _TrackedCapabilityRegistry:
    def __init__(self, registry: DefaultCapabilityRegistry, record_cleanup: Callable[[Callable[[], None]], None]) -> None:
        self._registry = registry
        self._record_cleanup = record_cleanup

    def names(self) -> list[str]:
        return self._registry.names()

    def get(self, name: str) -> Any | None:
        return self._registry.get(name)

    def register(self, name: str, description: str, handler: Callable[..., Any], *, override: bool = False) -> None:
        self._registry.register(name, description, handler, override=override)
        entry = self._registry.get(name)
        self._record_cleanup(lambda name=name, entry=entry: self._unregister_if_current(name, entry))

    def unregister(self, name: str) -> bool:
        return self._registry.unregister(name)

    def list(self) -> list[Any]:
        return self._registry.list()

    async def call(self, name: str, **kwargs: Any) -> Any:
        return await self._registry.call(name, **kwargs)

    def _unregister_if_current(self, name: str, entry: Any) -> bool:
        if self._registry.get(name) is not entry:
            return False
        return self._registry.unregister(name)


class _TrackedLifecycleHooks:
    def __init__(self, hooks: DefaultLifecycleHooks, record_cleanup: Callable[[Callable[[], None]], None]) -> None:
        self._hooks = hooks
        self._record_cleanup = record_cleanup

    def subscribe(self, stage: str, handler: Callable[..., Any], *, priority: int = 0) -> Callable[[], None]:
        unsubscribe = self._hooks.subscribe(stage, handler, priority=priority)
        self._record_cleanup(unsubscribe)
        return unsubscribe

    async def fire(self, stage: str, **kwargs: Any) -> Any:
        return await self._hooks.fire(stage, **kwargs)


# ---------------------------------------------------------------------------
# HostRuntimeFacade implementation
# ---------------------------------------------------------------------------


class _NullSkillRegistry:
    """当未注入 SkillManager 时的空桩对象。"""

    def register(self, skill: Any) -> None:
        pass

    def unregister(self, name: str) -> None:
        pass


class PluginHostFacade:
    def __init__(
        self,
        *,
        events: RuntimeInterceptionRegistry | None = None,
        output: OutputPort | None = None,
        commands: DefaultCommandRegistry | None = None,
        queries: DefaultQueryRegistry | None = None,
        capabilities: DefaultCapabilityRegistry | None = None,
        lifecycle: DefaultLifecycleHooks | None = None,
        skills: Any = None,
    ) -> None:
        self._events = events or _NullRuntimeInterceptionRegistry()
        self._output = output or NullOutput()
        self._commands = commands or DefaultCommandRegistry()
        self._queries = queries or DefaultQueryRegistry()
        self._capabilities = capabilities or DefaultCapabilityRegistry()
        self._lifecycle = lifecycle or DefaultLifecycleHooks()
        self._skills = skills or _NullSkillRegistry()

    @property
    def events(self) -> RuntimeInterceptionRegistry:
        return self._events

    def _set_events(self, events: RuntimeInterceptionRegistry) -> None:
        self._events = events

    @property
    def commands(self) -> DefaultCommandRegistry:
        return self._commands

    @property
    def queries(self) -> DefaultQueryRegistry:
        return self._queries

    @property
    def capabilities(self) -> DefaultCapabilityRegistry:
        return self._capabilities

    @property
    def output(self) -> OutputPort:
        return self._output

    @property
    def lifecycle(self) -> DefaultLifecycleHooks:
        return self._lifecycle

    def register_skill(self, skill: Any) -> None:
        """注册一个外部 Skill 模块。

        Args:
            skill: 实现 SkillModule 协议的对象（name, get_tools, execute）。
                   SkillManager 已有 register() 和 unregister() 方法以支持此接口。
        """
        self._skills.register(skill)

    def _set_skills(self, skills_registry: Any) -> None:
        """注入 SkillManager（用于创建顺序靠后的场景）。"""
        self._skills = skills_registry


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _NullRuntimeInterceptionRegistry:
    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
        return envelope


async def _call(handler: Callable[..., Any], **kwargs: Any) -> Any:
    sig = inspect.signature(handler)
    if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
        filtered = kwargs
    else:
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
    result = handler(**filtered)
    if inspect.isawaitable(result):
        return await result
    return result
