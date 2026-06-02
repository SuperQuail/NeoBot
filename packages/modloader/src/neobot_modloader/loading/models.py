from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    name: str
    version: str
    plugin: Any
    plugin_dir: Path
    config: dict[str, Any]
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    min_neobot_version: str | None = None
    python_dependencies: tuple[str, ...] = ()
    module_names: tuple[str, ...] = ()
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PluginLoadError:
    name: str
    plugin_dir: Path
    error: Exception


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    name: str
    version: str
    plugin_dir: Path
    description: str = ""
    author: str = ""
    enabled: bool = True
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    min_neobot_version: str | None = None
    python_dependencies: tuple[str, ...] = ()
    missing_python_dependencies: tuple[str, ...] = ()
    error: Exception | None = None
    source_path: Path | None = None


PluginLoadResult = LoadedPlugin | PluginLoadError
PluginDiscoveryResult = DiscoveredPlugin | PluginLoadError

