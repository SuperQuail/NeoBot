"""服务声明复用插件依赖图、生命周期与状态快照。"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

if TYPE_CHECKING:
    from neobot_modloader.runtime import PluginRuntime
    from neobot_modloader.loading.ordering import DependencyIssue
from neobot_modloader.dependency import PluginDependency, parse_dependencies


@dataclass(frozen=True, slots=True)
class ServiceManifest:
    """保留声明供卸载后的诊断与恢复使用，不保留插件实例。"""

    name: str
    version: str
    priority: int
    provides: tuple[str, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...]
    enabled: bool

    @classmethod
    def from_entry(cls, entry: Any) -> ServiceManifest:
        return cls(
            entry.name,
            entry.version,
            getattr(entry, "priority", 0),
            tuple(getattr(entry, "provides", ())),
            tuple(getattr(entry, "required", ())),
            tuple(getattr(entry, "optional", ())),
            getattr(entry, "enabled", True),
        )


async def reconcile_selection(runtime: PluginRuntime, previous: Mapping[str, Any]) -> None:
    current = runtime._service_providers
    changed = {
        name
        for name in previous.keys() | current.keys()
        if getattr(previous.get(name), "name", None) != getattr(current.get(name), "name", None)
    }
    if not changed:
        return
    for name in list(runtime.manager.names()):
        record = runtime.manager.get_record(name)
        if record is None or not runtime._service_provider_ready(name):
            continue
        if not any(dep.name in changed for dep in parse_dependencies(getattr(record.plugin, "required", ()))):
            continue
        issues = service_issues(runtime, record.plugin)
        if issues:
            runtime._remember_auto_disabled(name, record.plugin.dependencies, "; ".join(issues))
            await runtime.unload_plugin(name)
    for provider in {current[name].name for name in changed if name in current}:
        if runtime._service_provider_ready(provider):
            await runtime._cascade_restore_dependents(provider)


def providers_for(entries: Iterable[Any]) -> dict[str, Any]:
    providers = {}
    for entry in sorted(entries, key=lambda item: (-getattr(item, "priority", 0), item.name)):
        for name in getattr(entry, "provides", ()):
            providers.setdefault(name, entry)
    return providers


def service_edges(
    entry: Any, providers: Mapping[str, Any], hosts: Mapping[str, Any]
) -> tuple[list[PluginDependency], DependencyIssue | None]:
    from neobot_modloader.loading.ordering import DependencyIssue

    edges = []
    for declaration in parse_dependencies(getattr(entry, "required", ())):
        host = hosts.get(declaration.name)
        target = providers.get(declaration.name)
        if host:
            version = host.get("version", "")
        elif target:
            version = target.version
            edges.append(PluginDependency(target.name))
        else:
            return edges, DependencyIssue("service-missing", f"必需服务 {declaration.name} 缺失", declaration.name)
        if host and declaration.matches(version) is False:
            return edges, DependencyIssue(
                "service-version", f"必需服务版本不满足: {declaration.describe()}，当前 {version}", declaration.name
            )
    return edges, None


def declarations(runtime: PluginRuntime, name: str) -> Any:
    record = runtime.manager.get_record(name)
    return record.plugin if record else runtime._service_declarations.get(name)


def runtime_providers(runtime: PluginRuntime) -> dict[str, Any]:
    # 停用 / 自动禁用的插件不能继续占住声明：赢家不可用时回落到下一个可用提供者。
    entries = {
        name: entry
        for name, entry in runtime._service_declarations.items()
        if name not in runtime._auto_disabled and runtime._resolve_enabled_state(name, entry.enabled)
    }
    for name in runtime.manager.names():
        entries[name] = runtime.manager.get_record(name).plugin
    return providers_for(entries.values())


def refresh_selection(runtime: PluginRuntime) -> None:
    """只在清单刷新或插件换代时重建提供者索引。"""
    runtime._service_providers = runtime_providers(runtime)
    runtime.host.services.select({name: entry.name for name, entry in runtime._service_providers.items()})


def prerequisite_names(runtime: PluginRuntime, name: str) -> tuple[str, ...]:
    entry = declarations(runtime, name)
    if entry is None:
        return ()
    providers = runtime._service_providers
    return tuple(
        providers[dep.name].name
        if dep.name in providers and dep.name not in runtime._host_services()
        else f"service:{dep.name}"
        for dep in parse_dependencies(getattr(entry, "required", ()))
    )


def service_report(runtime: PluginRuntime, entry: Any) -> dict[str, Any]:
    providers = runtime._service_providers
    registry = runtime.host.services
    slots = []
    conflicts = []
    for kind in ("required", "optional", "provides"):
        for declaration in parse_dependencies(getattr(entry, kind, ())):
            target = providers.get(declaration.name)
            metadata = registry.metadata(declaration.name)
            provider = metadata["provider"] if metadata else target.name if target else None
            version = metadata["version"] if metadata else target.version if target else None
            status = "missing"
            if target or metadata:
                status = "unloaded"
                if provider != "__host__" and not runtime._resolve_enabled_state(
                    provider, getattr(target, "enabled", True)
                ):
                    status = "disabled"
                elif registry.has(declaration.name):
                    status = "loaded"
                if metadata and declaration.matches(version) is False:
                    status = "version"
            if kind == "provides" and provider and provider != entry.name:
                status = "conflict"
                conflicts.append(
                    dict(
                        service=declaration.name,
                        winner=provider,
                        loser=entry.name,
                        message=f"服务 {declaration.name} 由 {provider} 优先提供，{entry.name} 未选中",
                    )
                )
            labels = {
                "loaded": "已加载",
                "unloaded": "未加载",
                "disabled": "已停用",
                "missing": "缺失",
                "version": "版本不满足",
                "conflict": "提供者冲突",
            }
            title = {"required": "必需服务", "optional": "可选服务", "provides": "提供服务"}[kind]
            slots.append(
                dict(
                    service=declaration.name,
                    kind=kind,
                    status=status,
                    specifier=declaration.specifier,
                    provider=provider,
                    version=version,
                    message=f"{title} {declaration.name}（{labels[status]}）"
                    + (f"：需要 {declaration.specifier}，当前 {version}" if status == "version" else ""),
                )
            )
    record = runtime.manager.get_record(entry.name)
    tracked = getattr(getattr(record, "context", None), "_host", None)
    undeclared = tuple(sorted(getattr(getattr(tracked, "services", None), "undeclared", ())))
    blocked = any(slot["kind"] == "required" and slot["status"] != "loaded" for slot in slots)
    warning = bool(conflicts or undeclared or any(slot["status"] != "loaded" for slot in slots))
    return dict(
        services=tuple(slots),
        service_conflicts=tuple(conflicts),
        service_undeclared=undeclared,
        dependency_status="blocked" if blocked else "warning" if warning else "ok",
    )


def service_issues(runtime: PluginRuntime, entry: Any) -> list[str]:
    if entry is None or not getattr(entry, "required", ()):
        return []
    return [
        slot["message"]
        for slot in service_report(runtime, entry)["services"]
        if slot["kind"] == "required" and slot["status"] != "loaded"
    ]


def dependents(runtime: PluginRuntime, name: str, *, transitive: bool = False) -> list[str]:
    direct = runtime.manager.registry_view.dependents_of(name)
    direct += [
        candidate
        for candidate in runtime.manager.names()
        if candidate != name and name in prerequisite_names(runtime, candidate) and candidate not in direct
    ]
    if not transitive:
        return direct
    result = []
    pending = list(direct)
    while pending:
        candidate = pending.pop()
        if candidate == name or candidate in result:
            continue
        result.append(candidate)
        pending.extend(dependents(runtime, candidate))
    return result
