"""插件依赖解析与加载顺序。

依赖体系的目标：

1. 有前置插件的插件一定在前置插件之后加载（拓扑排序，同级按 priority 降序）；
2. 前置插件缺失、版本不满足、被停用或依赖成环时，**自动禁用**该插件
   （而不是让整个插件系统报错）——程序照常启动，前置插件满足后自动恢复；
3. 面板能拿到「为什么被自动禁用」的原因，便于一眼定位。

本模块只做纯计算，不知道运行时状态：调用方把已知但不可用的插件通过
unavailable 传进来（例如用户在面板里停用了 dashboard）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from neobot_modloader.dependency import PluginDependency, parse_dependencies
from neobot_modloader.loading.models import (
    DisabledPlugin,
    DiscoveredPlugin,
    LoadedPlugin,
    PluginDiscoveryResult,
    PluginLoadError,
    PluginLoadResult,
)

#: 前置插件不存在
CODE_MISSING = "dependency-missing"
#: 前置插件存在但版本不满足约束
CODE_VERSION = "dependency-version"
#: 前置插件存在但不可用（被停用 / 自身被自动禁用）
CODE_DISABLED = "dependency-disabled"
#: 依赖成环
CODE_CYCLE = "dependency-cycle"
#: 依赖声明本身非法（代码里声明的 dependencies 写错）
CODE_INVALID = "dependency-invalid"


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    """一个插件被自动禁用的原因。"""

    code: str
    reason: str
    dependency: str = ""


@dataclass(frozen=True, slots=True)
class PluginOrdering:
    """依赖解析结果。"""

    #: 可以加载的插件名（前置插件在前）
    ordered: tuple[str, ...]
    #: 被自动禁用的插件名 -> 原因
    blocked: Mapping[str, DependencyIssue]
    #: 重名插件（除首个之外的副本）
    duplicates: tuple[str, ...] = ()


def resolve_load_order(
    entries: Sequence[LoadedPlugin],
    *,
    unavailable: Mapping[str, str] | None = None,
) -> PluginOrdering:
    """解析依赖关系，返回加载顺序与自动禁用清单。

    Args:
        entries: 参与排序的插件（同名只保留第一个）。
        unavailable: 已知但当前不可用的插件名 -> 原因（例如「插件已停用」）。
    """
    unavailable = dict(unavailable or {})
    by_name: dict[str, LoadedPlugin] = {}
    duplicates: list[str] = []
    for entry in entries:
        if entry.name in by_name:
            duplicates.append(entry.name)
            continue
        by_name[entry.name] = entry

    specs: dict[str, tuple[PluginDependency, ...]] = {}
    blocked: dict[str, DependencyIssue] = {}
    for name, entry in by_name.items():
        try:
            specs[name] = parse_dependencies(entry.dependencies)
        except (TypeError, ValueError) as exc:
            specs[name] = ()
            blocked[name] = DependencyIssue(CODE_INVALID, f"依赖声明非法: {exc}")

    for name in _cycle_members(by_name, specs):
        blocked.setdefault(
            name,
            DependencyIssue(CODE_CYCLE, "插件依赖存在循环: " + " -> ".join(_cycle_path(by_name, specs, name))),
        )

    # 阻塞会沿依赖链传播：反复扫描直到不再变化（插件数量很小，收敛很快）
    changed = True
    while changed:
        changed = False
        for name, deps in specs.items():
            if name in blocked:
                continue
            issue = _evaluate(name, deps, by_name, blocked, unavailable)
            if issue is not None:
                blocked[name] = issue
                changed = True

    ordered: list[str] = []
    visited: set[str] = set()
    for name in sorted(by_name, key=lambda item: (-by_name[item].priority, item)):
        _visit(name, by_name, specs, blocked, visited, ordered)
    return PluginOrdering(
        ordered=tuple(ordered), blocked=blocked, duplicates=tuple(duplicates)
    )


def _evaluate(
    name: str,
    deps: Sequence[PluginDependency],
    by_name: Mapping[str, LoadedPlugin],
    blocked: Mapping[str, DependencyIssue],
    unavailable: Mapping[str, str],
) -> DependencyIssue | None:
    for dependency in deps:
        if dependency.name in blocked:
            return DependencyIssue(
                CODE_DISABLED,
                f"前置插件已被自动禁用: {dependency.describe()}",
                dependency.name,
            )
        target = by_name.get(dependency.name)
        if target is None:
            if dependency.name in unavailable:
                return DependencyIssue(
                    CODE_DISABLED,
                    f"前置插件不可用: {dependency.describe()}"
                    f"（{unavailable[dependency.name]}）",
                    dependency.name,
                )
            return DependencyIssue(
                CODE_MISSING, f"缺少前置插件: {dependency.describe()}", dependency.name
            )
        verdict = dependency.matches(target.version)
        if verdict is False:
            return DependencyIssue(
                CODE_VERSION,
                f"前置插件版本不满足: 需要 {dependency.describe()}，"
                f"当前 {dependency.name} {target.version}",
                dependency.name,
            )
    return None


def _visit(
    name: str,
    by_name: Mapping[str, LoadedPlugin],
    specs: Mapping[str, Sequence[PluginDependency]],
    blocked: Mapping[str, DependencyIssue],
    visited: set[str],
    ordered: list[str],
) -> None:
    if name in visited or name in blocked:
        return
    visited.add(name)
    for dependency in specs.get(name, ()):
        target = by_name.get(dependency.name)
        if target is not None:
            _visit(target.name, by_name, specs, blocked, visited, ordered)
    ordered.append(name)


def _dependency_graph(
    by_name: Mapping[str, LoadedPlugin],
    specs: Mapping[str, Sequence[PluginDependency]],
) -> dict[str, list[str]]:
    return {
        name: [dep.name for dep in deps if dep.name in by_name]
        for name, deps in specs.items()
    }


def _cycle_members(
    by_name: Mapping[str, LoadedPlugin],
    specs: Mapping[str, Sequence[PluginDependency]],
) -> list[str]:
    """返回所有处于依赖环上的插件名。"""
    graph = _dependency_graph(by_name, specs)
    state: dict[str, int] = {}
    members: list[str] = []

    def walk(node: str, stack: list[str]) -> None:
        state[node] = 1
        stack.append(node)
        for neighbour in graph.get(node, ()):
            if state.get(neighbour, 0) == 1:
                cycle = stack[stack.index(neighbour) :]
                for item in cycle:
                    if item not in members:
                        members.append(item)
            elif state.get(neighbour, 0) == 0:
                walk(neighbour, stack)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            walk(node, [])
    return members


def _cycle_path(
    by_name: Mapping[str, LoadedPlugin],
    specs: Mapping[str, Sequence[PluginDependency]],
    name: str,
) -> list[str]:
    """给出环上从 name 出发的一条闭合路径（用于错误文本）。"""
    graph = _dependency_graph(by_name, specs)
    path: list[str] = []
    seen: set[str] = set()
    node = name
    while node not in seen:
        seen.add(node)
        path.append(node)
        next_nodes = [item for item in graph.get(node, ()) if item in graph]
        if not next_nodes:
            break
        node = next_nodes[0]
    path.append(name)
    return path


def order_results(results: list[PluginLoadResult]) -> list[PluginLoadResult]:
    """加载路径排序：前置插件在前，依赖未满足的插件转成自动禁用条目。"""
    errors = [result for result in results if isinstance(result, PluginLoadError)]
    loaded = [result for result in results if isinstance(result, LoadedPlugin)]
    already_disabled = [result for result in results if isinstance(result, DisabledPlugin)]
    unavailable = {item.name: item.reason for item in already_disabled}
    ordering = resolve_load_order(loaded, unavailable=unavailable)
    by_name = {item.name: item for item in loaded}

    ordered: list[PluginLoadResult] = [by_name[name] for name in ordering.ordered]
    disabled: list[PluginLoadResult] = [
        _disabled_from(by_name[name], issue)
        for name, issue in sorted(ordering.blocked.items())
        if name in by_name
    ]
    duplicates = [
        PluginLoadError(
            name=name,
            plugin_dir=by_name[name].plugin_dir,
            error=ValueError(f"插件名重复: {name}"),
        )
        for name in ordering.duplicates
        if name in by_name
    ]
    return [*ordered, *already_disabled, *disabled, *errors, *duplicates]


def order_discovery_results(
    results: list[PluginDiscoveryResult],
) -> list[PluginDiscoveryResult]:
    """发现路径排序：给依赖未满足的插件标注自动禁用原因。"""
    errors = [result for result in results if isinstance(result, PluginLoadError)]
    discovered = [result for result in results if isinstance(result, DiscoveredPlugin)]
    enabled = [result for result in discovered if result.enabled]
    mapping = {result.name: result for result in enabled}
    unavailable: dict[str, str] = {}
    for result in discovered:
        if not result.enabled:
            unavailable[result.name] = "插件已停用"
        elif result.auto_disabled or result.disabled_reason:
            unavailable[result.name] = result.disabled_reason or "插件不可用"

    shims = [
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
            source=result.source,
        )
        for result in enabled
    ]
    ordering = resolve_load_order(shims, unavailable=unavailable)

    converted: list[PluginDiscoveryResult] = [mapping[name] for name in ordering.ordered]
    for name, issue in sorted(ordering.blocked.items()):
        converted.append(
            replace(
                mapping[name],
                disabled_reason=issue.reason,
                disabled_code=issue.code,
                auto_disabled=True,
            )
        )
    converted.extend(result for result in discovered if not result.enabled)
    converted.extend(errors)
    return converted


def _disabled_from(loaded: LoadedPlugin, issue: DependencyIssue) -> DisabledPlugin:
    return DisabledPlugin(
        name=loaded.name,
        plugin_dir=loaded.plugin_dir,
        reason=issue.reason,
        code=issue.code,
        version=loaded.version,
        description=loaded.description,
        author=loaded.author,
        dependencies=loaded.dependencies,
        source_path=loaded.source_path,
        source=loaded.source,
        module_names=loaded.module_names,
    )


__all__ = [
    "CODE_CYCLE",
    "CODE_DISABLED",
    "CODE_INVALID",
    "CODE_MISSING",
    "CODE_VERSION",
    "DependencyIssue",
    "PluginOrdering",
    "order_discovery_results",
    "order_results",
    "resolve_load_order",
]
