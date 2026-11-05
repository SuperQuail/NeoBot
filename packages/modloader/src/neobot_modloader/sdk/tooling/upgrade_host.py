"""维护验收只导入目标和它的前置闭包，不启动无关插件。"""

from contextlib import contextmanager
from pathlib import Path

from neobot_modloader.dependency import parse_dependencies
from neobot_modloader.loading.models import DiscoveredPlugin, LoadedPlugin, PluginLoadError
from neobot_modloader.loading.ordering import resolve_load_order
from neobot_modloader.loader import missing_python_dependencies
from neobot_modloader.runtime import PluginRuntime

from .models import ToolingError


@contextmanager
def upgrade_host_plan(runtime: PluginRuntime, target: Path, name: str):
    sources = {}
    # 官方身份优先，即使被停用或清单损坏，也不能由第三方同名副本接管。
    directories = [(directory, runtime.official_loader) for directory in runtime.builtin_plugin_dirs]
    directories.append((runtime.plugin_dir, runtime.loader))
    for directory, loader in directories:
        for entry in loader.discover_all(directory, resolve_dependencies=False):
            sources.setdefault(entry.name, (entry, loader))
    existing = sources.get(name)
    if existing is not None and existing[1].official:
        raise ToolingError("维护升级不能覆盖官方同名插件")
    loaded: dict[str, LoadedPlugin] = {}
    importing: set[str] = set()
    imported: list[LoadedPlugin] = []

    def visit(path, loader, expected):
        if expected in importing:
            raise ToolingError(f"维护升级前置依赖成环: {expected}")
        if expected in loaded:
            return
        entry = loader.load_one(path)
        if isinstance(entry, PluginLoadError):
            raise ToolingError(f"维护升级前置导入失败 ({expected}): {entry.error}")
        if not isinstance(entry, LoadedPlugin):
            raise ToolingError(f"维护升级前置未启用: {expected}")
        imported.append(entry)
        if entry.name != expected:
            raise ToolingError(f"维护升级插件身份不一致: 需要 {expected}，实际 {entry.name}")
        importing.add(expected)
        for dependency in parse_dependencies(entry.dependencies):
            source = sources.get(dependency.name)
            if source is None:
                raise ToolingError(f"维护升级缺少前置插件: {dependency.name}；官方插件需通过 --builtin-dir 指定来源")
            discovered, dependency_loader = source
            if not isinstance(discovered, DiscoveredPlugin) or not discovered.enabled:
                raise ToolingError(f"维护升级前置不可用: {dependency.name}")
            visit(discovered.source_path, dependency_loader, dependency.name)
        importing.remove(expected)
        loaded[expected] = entry

    try:
        visit(target, runtime.loader, name)
        ordered = resolve_load_order(list(loaded.values()))
        if ordered.blocked:
            raise ToolingError("; ".join(issue.reason for issue in ordered.blocked.values()))
        for entry in loaded.values():
            missing = missing_python_dependencies(entry.python_dependencies)
            incompatible = runtime._host_version_error(entry.name, entry.min_neobot_version)
            if missing or incompatible:
                raise ToolingError(incompatible or f"前置 {entry.name} 缺少 Python 依赖: {', '.join(missing)}")
        yield tuple(loaded[item] for item in ordered.ordered)
    finally:
        # 计划阶段尚未注册的模块不归 runtime 回收；异常与取消也必须清理。
        for entry in reversed(imported):
            runtime.loader.clear_module_cache(entry.module_names)
