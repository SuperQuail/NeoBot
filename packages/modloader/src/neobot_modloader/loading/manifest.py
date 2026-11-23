from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from neobot_modloader.dependency import parse_dependencies, parse_dependency

MAX_TAG_COUNT = 16
MAX_TAG_LENGTH = 32


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as file:
        return tomllib.load(file)


def read_dependencies(value: Any) -> tuple[str, ...]:
    """读取 plugin.toml 的 dependencies。

    每项是「插件名 + 可选版本约束」的字符串（例如 dashboard>=1.0.0）；
    这里只做格式校验并保留原始声明文本，拓扑排序时再解析成 PluginDependency。
    """
    if not isinstance(value, list):
        raise TypeError("plugin.toml 的 dependencies 必须是 string list")
    dependencies: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("plugin.toml 的 dependencies 必须是 string list")
        dependencies.append(parse_dependency(item).describe())
    return tuple(dependencies)


def read_python_dependencies(metadata: dict[str, Any]) -> tuple[str, ...]:
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


def read_optional_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"plugin.toml 的 {key} 必须是字符串")
    return value.strip()


def read_optional_bool(metadata: dict[str, Any], key: str, default: bool | None = None) -> bool | None:
    """读取可选的布尔字段；缺失时返回 default。"""
    if key not in metadata:
        return default
    value = metadata.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"plugin.toml 的 {key} 必须是 bool")
    return value


def read_tags(metadata: dict[str, Any]) -> tuple[str, ...]:
    value = metadata.get("tags")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError("plugin.toml 的 tags 必须是 string list")
    if len(value) > MAX_TAG_COUNT:
        raise ValueError(f"plugin.toml 的 tags 最多 {MAX_TAG_COUNT} 项")
    tags: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("plugin.toml 的 tags 必须是 string list")
        tag = item.strip()
        if not tag:
            raise ValueError("plugin.toml 的 tags 不能包含空字符串")
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"plugin.toml 的 tags 单项不能超过 {MAX_TAG_LENGTH} 字符")
        if tag not in tags:
            tags.append(tag)
    return tuple(tags)


def validate_manifest_conflicts(metadata: dict[str, Any], plugin: Any) -> None:
    manifest_name = metadata.get("name")
    if manifest_name is not None and str(manifest_name) != plugin.name:
        raise ValueError(f"plugin.toml name 与 Plugin(...) name 不一致: {manifest_name!r} != {plugin.name!r}")
    manifest_version = metadata.get("version")
    if manifest_version is not None and str(manifest_version) != plugin.version:
        raise ValueError(f"plugin.toml version 与 Plugin(...) version 不一致: {manifest_version!r} != {plugin.version!r}")


def read_service_list(value: Any, kind: str = "required") -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{kind} 必须是 string list")
    parsed = parse_dependencies(value)
    if any(re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", item.name) is None or "__" in item.name for item in parsed):
        raise ValueError("服务名必须以小写字母开头，只含小写字母、数字、点、连字符和下划线，且不能含 __")
    if kind == "provides" and len(parsed) > 16:
        raise ValueError("provides 最多声明 16 个服务")
    if kind == "provides" and any(item.specifier for item in parsed):
        raise ValueError("provides 只允许服务名，版本通过注册指定")
    return tuple(item.describe() for item in parsed)


def read_services(metadata: dict[str, Any], plugin: Any = None) -> dict[str, tuple[str, ...]]:
    result = {}
    for kind in ("provides", "required", "optional"):
        code = tuple(getattr(plugin, kind, ())) if plugin is not None else ()
        result[kind] = read_service_list(metadata.get(kind, code), kind)
        explicit = getattr(plugin, "_explicit_service_fields", ())
        if kind in metadata and (code or kind in explicit) and code != result[kind]:
            raise ValueError(f"plugin.toml {kind} 与 Plugin(...) 不一致")
    names: set[str] = set()
    for kind, values in result.items():
        current = {item.name for item in parse_dependencies(values)}
        if names.intersection(current):
            raise ValueError("provides、required 与 optional 不能声明同一服务")
        names.update(current)
    return result
