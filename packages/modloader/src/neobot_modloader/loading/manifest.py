from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from neobot_modloader.plugins.registration import validate_plugin_name

MAX_TAG_COUNT = 16
MAX_TAG_LENGTH = 32


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as file:
        return tomllib.load(file)


def read_dependencies(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError("plugin.toml 的 dependencies 必须是 string list")
    dependencies: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("plugin.toml 的 dependencies 必须是 string list")
        dependency = str(item)
        validate_plugin_name(dependency)
        dependencies.append(dependency)
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
