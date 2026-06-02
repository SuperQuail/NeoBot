from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_modloader.loading.importer import PluginModuleImporter
from neobot_modloader.loading.manifest import (
    read_dependencies,
    read_manifest,
    read_python_dependencies,
    validate_manifest_conflicts,
)
from neobot_modloader.loading.models import (
    DiscoveredPlugin,
    LoadedPlugin,
    PluginDiscoveryResult,
    PluginLoadError,
    PluginLoadResult,
)
from neobot_modloader.loading.ordering import order_discovery_results, order_results
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.registration import validate_plugin_name


class FilesystemPluginLoader:
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._importer = PluginModuleImporter()

    def discover_all(self, plugin_dir: Path) -> list[PluginDiscoveryResult]:
        plugin_dir = plugin_dir.resolve()
        if not plugin_dir.exists():
            self._logger.info(f"插件目录不存在，已按空目录处理: {plugin_dir}")
            return []
        if not plugin_dir.is_dir():
            return [PluginLoadError(name=plugin_dir.name, plugin_dir=plugin_dir, error=NotADirectoryError(str(plugin_dir)))]

        results: list[PluginDiscoveryResult] = []
        for entry in sorted(plugin_dir.iterdir(), key=lambda item: item.name):
            if entry.name.startswith("_"):
                continue
            if entry.is_file() and entry.suffix == ".py":
                results.append(self._discover_file(entry))
            elif entry.is_dir() and (entry / "__init__.py").is_file():
                result = self._discover_package(entry)
                if result is not None:
                    results.append(result)
        return order_discovery_results(results)

    def load_all(self, plugin_dir: Path) -> list[PluginLoadResult]:
        plugin_dir = plugin_dir.resolve()
        if not plugin_dir.exists():
            self._logger.info(f"插件目录不存在，已按空目录处理: {plugin_dir}")
            return []
        if not plugin_dir.is_dir():
            return [PluginLoadError(name=plugin_dir.name, plugin_dir=plugin_dir, error=NotADirectoryError(str(plugin_dir)))]

        results: list[PluginLoadResult] = []
        for entry in sorted(plugin_dir.iterdir(), key=lambda item: item.name):
            if entry.name.startswith("_"):
                continue
            if entry.is_file() and entry.suffix == ".py":
                results.append(self._load_file(entry))
            elif entry.is_dir() and (entry / "__init__.py").is_file():
                result = self._load_package(entry)
                if result is not None:
                    results.append(result)
        return order_results(results)

    def load_one(self, plugin_path: Path) -> PluginLoadResult | None:
        plugin_path = plugin_path.resolve()
        if plugin_path.is_file() and plugin_path.suffix == ".py":
            return self._load_file(plugin_path)
        if plugin_path.is_dir() and (plugin_path / "__init__.py").is_file():
            return self._load_package(plugin_path)
        return PluginLoadError(name=plugin_path.name, plugin_dir=plugin_path, error=FileNotFoundError(str(plugin_path)))

    def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
        self._importer.clear_module_cache(module_names)

    def _discover_file(self, path: Path) -> PluginDiscoveryResult:
        name = path.stem
        try:
            self._validate_plugin_name(name)
            return DiscoveredPlugin(name=name, version="0.1.0", plugin_dir=path.parent, source_path=path)
        except Exception as exc:
            return PluginLoadError(name=name, plugin_dir=path.parent, error=exc)

    def _discover_package(self, path: Path) -> PluginDiscoveryResult | None:
        manifest_name = path.name
        try:
            metadata = read_manifest(path / "plugin.toml")
            enabled = metadata.get("enabled", True)
            if not isinstance(enabled, bool):
                raise TypeError("plugin.toml 的 enabled 必须是 bool")
            name = str(metadata.get("name") or path.name)
            self._validate_plugin_name(name)
            version = str(metadata.get("version") or "0.1.0")
            description = str(metadata.get("description") or "")
            author = str(metadata.get("author") or "")
            min_neobot_version_raw = metadata.get("min_neobot_version")
            min_neobot_version = str(min_neobot_version_raw) if min_neobot_version_raw is not None else None
            priority = metadata.get("priority", 0)
            if not isinstance(priority, int):
                raise TypeError("plugin.toml 的 priority 必须是 int")
            dependencies = read_dependencies(metadata.get("dependencies") or [])
            python_dependencies = read_python_dependencies(metadata)
            return DiscoveredPlugin(
                name=name,
                version=version,
                plugin_dir=path,
                description=description,
                author=author,
                enabled=enabled,
                dependencies=dependencies,
                priority=priority,
                min_neobot_version=min_neobot_version,
                python_dependencies=python_dependencies,
                missing_python_dependencies=missing_python_dependencies(python_dependencies),
                source_path=path,
            )
        except Exception as exc:
            return PluginLoadError(name=manifest_name, plugin_dir=path, error=exc)

    def _load_file(self, path: Path) -> PluginLoadResult:
        name = path.stem
        try:
            self._validate_plugin_name(name)
            module = self._importer.import_module(path, name)
            plugin = self._create_plugin(module)
            plugin_name = str(getattr(plugin, "name", name) or name)
            self._validate_plugin_name(plugin_name)
            version = str(getattr(plugin, "version", "0.1.0") or "0.1.0")
            return LoadedPlugin(
                name=plugin_name,
                version=version,
                plugin=plugin,
                plugin_dir=path.parent,
                config={},
                description=str(getattr(plugin, "description", "") or ""),
                author=str(getattr(plugin, "author", "") or ""),
                dependencies=tuple(getattr(plugin, "dependencies", ()) or ()),
                priority=int(getattr(plugin, "priority", 0) or 0),
                min_neobot_version=getattr(plugin, "min_neobot_version", None),
                python_dependencies=tuple(getattr(plugin, "python_dependencies", ()) or ()),
                module_names=self._importer.last_module_names,
                source_path=path,
            )
        except Exception as exc:
            self._logger.exception(f"插件加载失败 ({path}): {exc}")
            return PluginLoadError(name=name, plugin_dir=path.parent, error=exc)

    def _load_package(self, path: Path) -> PluginLoadResult | None:
        manifest_name = path.name
        try:
            metadata = read_manifest(path / "plugin.toml")
            enabled = metadata.get("enabled", True)
            if not isinstance(enabled, bool):
                raise TypeError("plugin.toml 的 enabled 必须是 bool")
            if not enabled:
                self._logger.info(f"插件已禁用，跳过加载: {path}")
                return None
            name = str(metadata.get("name") or path.name)
            self._validate_plugin_name(name)
            version = str(metadata.get("version") or "0.1.0")
            description = str(metadata.get("description") or "")
            author = str(metadata.get("author") or "")
            min_neobot_version_raw = metadata.get("min_neobot_version")
            min_neobot_version = str(min_neobot_version_raw) if min_neobot_version_raw is not None else None
            priority = metadata.get("priority", 0)
            if not isinstance(priority, int):
                raise TypeError("plugin.toml 的 priority 必须是 int")
            dependencies = read_dependencies(metadata.get("dependencies") or [])
            python_dependencies = read_python_dependencies(metadata)
            config = metadata.get("config") or {}
            if not isinstance(config, dict):
                raise TypeError("plugin.toml 的 [config] 必须是 table")

            module = self._importer.import_module(path / "__init__.py", name)
            plugin = self._create_plugin(module)
            validate_manifest_conflicts(metadata, plugin)
            plugin_name = str(getattr(plugin, "name", name) or name)
            self._validate_plugin_name(plugin_name)
            plugin_version = str(getattr(plugin, "version", version) or version)
            if "dependencies" not in metadata:
                dependencies = tuple(getattr(plugin, "dependencies", ()) or ())
            if not any(key in metadata for key in ("python_dependencies", "pypi_dependencies", "requirements")):
                python_dependencies = tuple(getattr(plugin, "python_dependencies", ()) or ())
            if "priority" not in metadata:
                priority = int(getattr(plugin, "priority", 0) or 0)
            if min_neobot_version is None:
                min_neobot_version = getattr(plugin, "min_neobot_version", None)
            return LoadedPlugin(
                name=plugin_name,
                version=plugin_version,
                plugin=plugin,
                plugin_dir=path,
                config=dict(config),
                description=str(getattr(plugin, "description", description) or description),
                author=str(getattr(plugin, "author", author) or author),
                dependencies=dependencies,
                priority=priority,
                min_neobot_version=min_neobot_version,
                python_dependencies=python_dependencies,
                module_names=self._importer.last_module_names,
                source_path=path,
            )
        except Exception as exc:
            self._logger.exception(f"插件加载失败 ({path}): {exc}")
            return PluginLoadError(name=manifest_name, plugin_dir=path, error=exc)

    def _create_plugin(self, module: ModuleType) -> Plugin:
        plugin = getattr(module, "plugin", None)
        if isinstance(plugin, Plugin):
            return plugin

        raise ValueError("插件模块必须导出 plugin = Plugin(...)")

    def _validate_plugin_name(self, name: str) -> None:
        if not name:
            raise ValueError("插件名不能为空")
        try:
            validate_plugin_name(name)
        except ValueError as exc:
            raise ValueError(f"非法插件名: {name!r}") from exc


def requirement_distribution_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    if match is None:
        raise ValueError(f"非法 Python 依赖声明: {requirement!r}")
    return match.group(1).replace("_", "-")


def is_python_dependency_installed(requirement: str) -> bool:
    name = requirement_distribution_name(requirement)
    try:
        importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def missing_python_dependencies(requirements: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(requirement for requirement in requirements if not is_python_dependency_installed(requirement))
