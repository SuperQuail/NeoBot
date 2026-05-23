from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class RuntimeEnvelope:
    kind: str
    stage: str
    source: str = ""
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    consumed: bool = False
    result: Any = None
    error: str | None = None

    def consume(self, result: Any = None) -> None:
        self.consumed = True
        self.result = result

    def annotate(self, key: str, value: Any) -> None:
        self.trace[key] = value


RuntimeInterceptor = Callable[[RuntimeEnvelope], Any]


@runtime_checkable
class RuntimeInterceptionRegistry(Protocol):
    def subscribe(
        self,
        handler: RuntimeInterceptor,
        *,
        kind: str | None = None,
        stage: str | None = None,
        source: str | None = None,
        target: str | None = None,
        priority: int = 0,
        timeout: float | None = None,
    ) -> Any: ...

    async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope: ...
