from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_modloader.plugin import FunctionPlugin


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


class FilesystemPluginLoader:
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        self._last_module_names: tuple[str, ...] = ()

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
        return self._order_discovery_results(results)

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
        return self._order_results(results)

    def load_one(self, plugin_path: Path) -> PluginLoadResult | None:
        plugin_path = plugin_path.resolve()
        if plugin_path.is_file() and plugin_path.suffix == ".py":
            return self._load_file(plugin_path)
        if plugin_path.is_dir() and (plugin_path / "__init__.py").is_file():
            return self._load_package(plugin_path)
        return PluginLoadError(name=plugin_path.name, plugin_dir=plugin_path, error=FileNotFoundError(str(plugin_path)))

    def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
        for module_name in sorted(module_names, key=len, reverse=True):
            for cached_name in list(sys.modules):
                if cached_name == module_name or cached_name.startswith(f"{module_name}."):
                    sys.modules.pop(cached_name, None)

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
            metadata = self._read_manifest(path / "plugin.toml")
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
            dependencies = self._read_dependencies(metadata.get("dependencies") or [])
            python_dependencies = self._read_python_dependencies(metadata)
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
            module = self._import_module(path, name)
            plugin = self._create_plugin(module, name=name, version="0.1.0")
            plugin_name = str(getattr(plugin, "name", name) or name)
            self._validate_plugin_name(plugin_name)
            version = str(getattr(plugin, "version", "0.1.0") or "0.1.0")
            return LoadedPlugin(
                name=plugin_name,
                version=version,
                plugin=plugin,
                plugin_dir=path.parent,
                config={},
                description="",
                author="",
                dependencies=(),
                priority=0,
                min_neobot_version=None,
                python_dependencies=(),
                module_names=self._last_module_names,
                source_path=path,
            )
        except Exception as exc:
            self._logger.exception(f"插件加载失败 ({path}): {exc}")
            return PluginLoadError(name=name, plugin_dir=path.parent, error=exc)

    def _load_package(self, path: Path) -> PluginLoadResult | None:
        manifest_name = path.name
        try:
            metadata = self._read_manifest(path / "plugin.toml")
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
            dependencies = self._read_dependencies(metadata.get("dependencies") or [])
            python_dependencies = self._read_python_dependencies(metadata)
            config = metadata.get("config") or {}
            if not isinstance(config, dict):
                raise TypeError("plugin.toml 的 [config] 必须是 table")

            module = self._import_module(path / "__init__.py", name)
            plugin = self._create_plugin(module, name=name, version=version)
            plugin_name = str(getattr(plugin, "name", name) or name)
            self._validate_plugin_name(plugin_name)
            plugin_version = str(getattr(plugin, "version", version) or version)
            return LoadedPlugin(
                name=plugin_name,
                version=plugin_version,
                plugin=plugin,
                plugin_dir=path,
                config=dict(config),
                description=description,
                author=author,
                dependencies=dependencies,
                priority=priority,
                min_neobot_version=min_neobot_version,
                python_dependencies=python_dependencies,
                module_names=self._last_module_names,
                source_path=path,
            )
        except Exception as exc:
            self._logger.exception(f"插件加载失败 ({path}): {exc}")
            return PluginLoadError(name=manifest_name, plugin_dir=path, error=exc)

    def _read_manifest(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        with path.open("rb") as file:
            return tomllib.load(file)

    def _read_dependencies(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise TypeError("plugin.toml 的 dependencies 必须是 string list")
        dependencies: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError("plugin.toml 的 dependencies 必须是 string list")
            dependency = str(item)
            self._validate_plugin_name(dependency)
            dependencies.append(dependency)
        return tuple(dependencies)

    def _read_python_dependencies(self, metadata: dict[str, Any]) -> tuple[str, ...]:
        value = metadata.get("python_dependencies")
        if value is None:
            value = metadata.get("pypi_dependencies")
        if value is None:
            value = metadata.get("requirements")
        if value is None:
            return ()
        if not isinstance(value, list):
            raise TypeError("plugin.toml 的 python_dependencies 必须是 string list")
        dependencies: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError("plugin.toml 的 python_dependencies 必须是 string list")
            requirement = item.strip()
            if not requirement:
                raise ValueError("plugin.toml 的 python_dependencies 不能包含空字符串")
            dependencies.append(requirement)
        return tuple(dependencies)

    def _order_discovery_results(self, results: list[PluginDiscoveryResult]) -> list[PluginDiscoveryResult]:
        loaded_like: list[PluginLoadResult] = []
        mapping: dict[str, DiscoveredPlugin] = {}
        for result in results:
            if isinstance(result, PluginLoadError):
                loaded_like.append(result)
            else:
                loaded_like.append(
                    LoadedPlugin(
                        name=result.name,
                        version=result.version,
                        plugin=object(),
                        plugin_dir=result.plugin_dir,
                        config={},
                        description=result.description,
                        author=result.author,
                        dependencies=result.dependencies,
                        priority=result.priority,
                        min_neobot_version=result.min_neobot_version,
                        python_dependencies=result.python_dependencies,
                        source_path=result.source_path,
                    )
                )
                mapping[result.name] = result
        ordered = self._order_results(loaded_like)
        converted: list[PluginDiscoveryResult] = []
        for result in ordered:
            if isinstance(result, PluginLoadError):
                converted.append(result)
            else:
                converted.append(mapping[result.name])
        return converted

    def _order_results(self, results: list[PluginLoadResult]) -> list[PluginLoadResult]:
        errors = [result for result in results if isinstance(result, PluginLoadError)]
        loaded = [result for result in results if isinstance(result, LoadedPlugin)]
        by_name: dict[str, LoadedPlugin] = {}
        ordered_errors: list[PluginLoadError] = list(errors)

        for plugin in loaded:
            if plugin.name in by_name:
                ordered_errors.append(PluginLoadError(name=plugin.name, plugin_dir=plugin.plugin_dir, error=ValueError(f"插件名重复: {plugin.name}")))
                continue
            by_name[plugin.name] = plugin

        missing_or_duplicate_errors: list[PluginLoadError] = []
        for plugin in list(by_name.values()):
            missing = [name for name in plugin.dependencies if name not in by_name]
            if missing:
                by_name.pop(plugin.name, None)
                missing_or_duplicate_errors.append(PluginLoadError(name=plugin.name, plugin_dir=plugin.plugin_dir, error=ValueError(f"插件依赖缺失: {', '.join(missing)}")))

        ordered: list[LoadedPlugin] = []
        visiting: set[str] = set()
        visited: set[str] = set()
        cycle_errors: list[PluginLoadError] = []

        def visit(plugin: LoadedPlugin) -> None:
            if plugin.name in visited:
                return
            if plugin.name in visiting:
                raise ValueError(f"插件依赖存在循环: {plugin.name}")
            visiting.add(plugin.name)
            for dependency in plugin.dependencies:
                dependency_plugin = by_name.get(dependency)
                if dependency_plugin is not None:
                    visit(dependency_plugin)
            visiting.remove(plugin.name)
            visited.add(plugin.name)
            ordered.append(plugin)

        for plugin in sorted(by_name.values(), key=lambda item: (-item.priority, item.name)):
            try:
                visit(plugin)
            except ValueError as exc:
                cycle_errors.append(PluginLoadError(name=plugin.name, plugin_dir=plugin.plugin_dir, error=exc))

        if cycle_errors:
            cycle_names = {error.name for error in cycle_errors}
            ordered = [plugin for plugin in ordered if plugin.name not in cycle_names]

        return [*ordered, *ordered_errors, *missing_or_duplicate_errors, *cycle_errors]

    def _import_module(self, path: Path, plugin_name: str) -> ModuleType:
        importlib.invalidate_caches()
        pycache = path.parent / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache, ignore_errors=True)
        before = {name for name in sys.modules if name.startswith("neobot_user_plugins.")}
        module_name = self._module_name(path, plugin_name)
        sys.modules.setdefault("neobot_user_plugins", ModuleType("neobot_user_plugins"))
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建插件模块 spec: {path}")
        module = importlib.util.module_from_spec(spec)
        if path.name == "__init__.py":
            module.__package__ = module_name
            module.__path__ = [str(path.parent)]
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        after = {
            name
            for name in sys.modules
            if name == module_name
            or name.startswith(f"{module_name}.")
            or (name not in before and name.startswith("neobot_user_plugins."))
        }
        self._last_module_names = tuple(sorted(after))
        return module

    def _create_plugin(self, module: ModuleType, *, name: str, version: str) -> Any:
        setup = getattr(module, "setup", None)
        if callable(setup):
            return FunctionPlugin(name=name, version=version, setup=setup)

        plugin = getattr(module, "plugin", None)
        if plugin is not None:
            return plugin

        create_plugin = getattr(module, "create_plugin", None)
        if callable(create_plugin):
            return create_plugin()

        raise ValueError("插件模块未导出 setup(ctx)、plugin 或 create_plugin()")

    def _module_name(self, path: Path, plugin_name: str) -> str:
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        safe_name = re.sub(r"\W", "_", plugin_name)
        return f"neobot_user_plugins.{safe_name}_{digest}"

    def _validate_plugin_name(self, name: str) -> None:
        if not name:
            raise ValueError("插件名不能为空")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
            raise ValueError(f"非法插件名: {name!r}")


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
