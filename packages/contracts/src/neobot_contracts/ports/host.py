"""Unified plugin-facing host contracts: facade, commands, queries, capabilities, lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from neobot_contracts.ports.output import OutputPort
from neobot_contracts.ports.runtime_event import RuntimeInterceptionRegistry

# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CommandSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CommandRegistry(Protocol):
    def register(self, name: str, description: str, handler: Callable[..., Any], *, schema: dict[str, Any] | None = None, override: bool = False) -> None: ...

    def unregister(self, name: str) -> bool: ...

    def names(self) -> list[str]: ...

    def get(self, name: str) -> CommandSpec | None: ...

    async def call(self, name: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Query registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class QuerySpec:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class QueryRegistry(Protocol):
    def register(self, name: str, description: str, handler: Callable[..., Any], *, schema: dict[str, Any] | None = None, override: bool = False) -> None: ...

    def unregister(self, name: str) -> bool: ...

    def names(self) -> list[str]: ...

    def get(self, name: str) -> QuerySpec | None: ...

    async def query(self, name: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CapabilitySpec:
    name: str
    description: str
    handler: Callable[..., Any]


@runtime_checkable
class CapabilityRegistry(Protocol):
    def register(self, name: str, description: str, handler: Callable[..., Any], *, override: bool = False) -> None: ...

    def unregister(self, name: str) -> bool: ...

    def names(self) -> list[str]: ...

    def get(self, name: str) -> CapabilitySpec | None: ...

    def list(self) -> list[CapabilitySpec]: ...

    async def call(self, name: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


@runtime_checkable
class LifecycleHooks(Protocol):
    async def fire(self, stage: str, **kwargs: Any) -> Any: ...

    def subscribe(self, stage: str, handler: Callable[..., Any], *, priority: int = 0) -> Callable[[], None]: ...


# ---------------------------------------------------------------------------
# Host runtime facade
# ---------------------------------------------------------------------------


@runtime_checkable
class HostRuntimeFacade(Protocol):
    @property
    def events(self) -> RuntimeInterceptionRegistry: ...

    @property
    def commands(self) -> CommandRegistry: ...

    @property
    def queries(self) -> QueryRegistry: ...

    @property
    def capabilities(self) -> CapabilityRegistry: ...

    @property
    def output(self) -> OutputPort: ...

    @property
    def lifecycle(self) -> LifecycleHooks: ...
