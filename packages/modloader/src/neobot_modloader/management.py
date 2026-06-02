from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PluginOperationResult:
    ok: bool
    name: str
    state: str | None = None
    error: str | None = None
    requires_restart: bool = False
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class PluginSnapshot:
    name: str
    version: str = "0.1.0"
    state: str = "unloaded"
    enabled: bool = True
    path: Path | None = None
    kind: str = "unknown"
    error: str | None = None
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    python_dependencies: tuple[str, ...] = ()
    missing_python_dependencies: tuple[str, ...] = ()


class PluginControlFacade:
    """Narrow runtime management facade exposed to plugins."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def load_path(
        self,
        path: Path,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        return await self._runtime.load_plugin_path(
            path,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )

    async def unload(self, name: str) -> PluginOperationResult:
        return await self._runtime.unload_plugin(name)

    async def reload(
        self,
        name: str,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        return await self._runtime.reload_plugin_result(
            name,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )

    async def start(self, name: str) -> PluginOperationResult:
        return await self._runtime.start_plugin(name)

    async def stop(self, name: str) -> PluginOperationResult:
        return await self._runtime.stop_plugin(name)

    def snapshot(self) -> list[PluginSnapshot]:
        return self._runtime.snapshot_plugins()
