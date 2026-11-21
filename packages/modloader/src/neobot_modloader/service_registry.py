"""按提供者优先级选择服务，并按注册代际回收实例。"""

from __future__ import annotations
from typing import Any
from collections.abc import Callable


class ServiceUnavailable(KeyError):
    """必需服务尚无可用实例。"""


class DefaultServiceRegistry:
    def __init__(self) -> None:
        self._candidates: dict[str, dict[str, dict[str, Any]]] = {}
        self._selection: dict[str, str] = {}
        self.ready: Callable[[str], bool] = lambda provider: True

    def select(self, providers: dict[str, str]) -> None:
        self._selection = dict(providers)

    def register(
        self,
        name: str,
        service: Any,
        *,
        description: str = "",
        override: bool = False,
        provider: str = "__host__",
        version: str = "",
        priority: int = 0,
        owner: object | None = None,
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("服务名必须是非空字符串")
        name = name.strip()
        entries = self._candidates.setdefault(name, {})
        if provider in entries and not override:
            raise ValueError(f"服务已注册: {name!r}")
        entry = dict(
            service=service,
            description=str(description or ""),
            provider=provider,
            version=version,
            priority=priority,
            owner=owner,
        )
        entries[provider] = entry
        return entry

    def unregister(self, name: str, *, provider: str | None = None, entry: dict[str, Any] | None = None) -> bool:
        entries = self._candidates.get(name, {})
        if provider is None:
            current = self.metadata(name)
            provider = current.get("provider") if current else None
        if provider not in entries or (entry is not None and entries[provider] is not entry):
            return False
        del entries[provider]
        if not entries:
            self._candidates.pop(name, None)
        return True

    def metadata(self, name: str) -> dict[str, Any] | None:
        entries = self._candidates.get(name, {})
        if "__host__" in entries:
            return entries["__host__"]
        selected = self._selection.get(name)
        if selected is not None:
            return entries.get(selected)
        return min(entries.values(), key=lambda e: (-e["priority"], e["provider"]), default=None)

    def get(self, name: str, default: Any = None) -> Any:
        entry = self.metadata(name)
        if entry is None or not self.ready(entry["provider"]):
            return default
        return entry["service"] if entry["service"] is not None else default

    def require(self, name: str) -> Any:
        value = self.get(name)
        if value is None:
            raise ServiceUnavailable(f"宿主服务未注册: {name!r}；可用服务: {', '.join(self.names()) or '（无）'}")
        return value

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def names(self) -> list[str]:
        return list(self._candidates)

    def describe(self) -> list[dict[str, Any]]:
        return [
            dict(
                name=name,
                description=entry["description"],
                available=self.has(name),
                provider=entry["provider"],
                version=entry["version"],
            )
            for name in self.names()
            if (entry := self.metadata(name)) is not None
        ]


class ServiceAccess:
    """每次访问都重新解析服务，不缓存可能已被回收的实例。"""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def get(self, name: str, default: Any = None) -> Any:
        return self._registry.get(name, default)

    def require(self, name: str) -> Any:
        return self._registry.require(name)

    def provide(self, name: str, service: Any, *, version: str | None = None, description: str = "") -> None:
        self._registry.register(name, service, version=version, description=description)

    def has(self, name: str) -> bool:
        return self._registry.has(name)

    def describe(self) -> list[dict[str, Any]]:
        return self._registry.describe()
