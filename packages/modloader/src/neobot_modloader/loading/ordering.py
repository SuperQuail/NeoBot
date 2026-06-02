from __future__ import annotations

from neobot_modloader.loading.models import (
    DiscoveredPlugin,
    LoadedPlugin,
    PluginDiscoveryResult,
    PluginLoadError,
    PluginLoadResult,
)


def order_discovery_results(results: list[PluginDiscoveryResult]) -> list[PluginDiscoveryResult]:
    loaded_like: list[PluginLoadResult] = []
    mapping: dict[str, DiscoveredPlugin] = {}
    for result in results:
        if isinstance(result, PluginLoadError):
            loaded_like.append(result)
        else:
            # discover 阶段不导入插件，用 LoadedPlugin 形状复用同一套依赖排序逻辑。
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
    ordered = order_results(loaded_like)
    converted: list[PluginDiscoveryResult] = []
    for result in ordered:
        if isinstance(result, PluginLoadError):
            converted.append(result)
        else:
            converted.append(mapping[result.name])
    return converted


def order_results(results: list[PluginLoadResult]) -> list[PluginLoadResult]:
    errors = [result for result in results if isinstance(result, PluginLoadError)]
    loaded = [result for result in results if isinstance(result, LoadedPlugin)]
    by_name: dict[str, LoadedPlugin] = {}
    ordered_errors: list[PluginLoadError] = list(errors)

    for plugin in loaded:
        if plugin.name in by_name:
            ordered_errors.append(
                PluginLoadError(
                    name=plugin.name,
                    plugin_dir=plugin.plugin_dir,
                    error=ValueError(f"插件名重复: {plugin.name}"),
                )
            )
            continue
        by_name[plugin.name] = plugin

    missing_or_duplicate_errors: list[PluginLoadError] = []
    for plugin in list(by_name.values()):
        missing = [name for name in plugin.dependencies if name not in by_name]
        if missing:
            by_name.pop(plugin.name, None)
            missing_or_duplicate_errors.append(
                PluginLoadError(
                    name=plugin.name,
                    plugin_dir=plugin.plugin_dir,
                    error=ValueError(f"插件依赖缺失: {', '.join(missing)}"),
                )
            )

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
