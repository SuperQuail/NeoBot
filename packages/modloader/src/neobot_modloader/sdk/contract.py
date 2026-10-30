"""在不导入作者代码的情况下验证随包静态契约。"""

from __future__ import annotations

import json
import re
from typing import Any

from packaging.version import InvalidVersion, Version

from neobot_modloader.plugins.registration import validate_plugin_name

from .guides import guide_command_errors, guide_form_errors
from .schema import sanitize_schema, schema_field_paths, schema_structure_errors
from .surface import validate_view_entry

_ID = re.compile(r"[a-z][a-z0-9_.-]*\Z")
_PERMISSIONS = {"read", "operate", "manage"}


def _entries(document: dict[str, Any], key: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    values = document.get(key, [])
    if not isinstance(values, list):
        errors.append(f"{key} 必须是列表")
        return {}
    entries = {}
    for index, item in enumerate(values):
        identifier = item.get("id") if isinstance(item, dict) else None
        if (
            not isinstance(identifier, str)
            or not _ID.fullmatch(identifier)
            or any(not part for part in identifier.split("."))
        ):
            errors.append(f"{key}[{index}].id 格式无效")
            continue
        if identifier in entries:
            errors.append(f"{key} 存在重复 ID: {identifier}")
            continue
        entries[identifier] = item
    return entries


def _compare_schema_object(original: dict[str, Any], cleaned: dict[str, Any], location: str, errors: list[str]) -> None:
    for key, item in original.items():
        target = f"{location}.{key}"
        if key in {"default", "examples", "const", "enum"} and cleaned.get(key) != item:
            errors.append(f"{target} 含敏感值，必须重新导出契约")
            continue
        if key in cleaned:
            _compare_schema_values(item, cleaned[key], target, errors)


def _compare_schema_values(original: Any, cleaned: Any, location: str, errors: list[str]) -> None:
    if isinstance(original, dict) and isinstance(cleaned, dict):
        _compare_schema_object(original, cleaned, location, errors)
        return
    if isinstance(original, list) and isinstance(cleaned, list):
        for index, (before, after) in enumerate(zip(original, cleaned)):
            _compare_schema_values(before, after, f"{location}[{index}]", errors)


def _validate_schema(value: Any, location: str, errors: list[str]) -> dict[str, Any] | None:
    """先校验静态结构，再清洗默认值；只有可安全遍历的对象才用于收集字段路径。"""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, dict):
        errors.append(f"{location} 必须是 JSON Schema 对象、布尔值或 null")
        return None
    structure_errors = schema_structure_errors(value, location)
    if structure_errors:
        errors.extend(structure_errors)
        return None
    public = sanitize_schema(value)
    _compare_schema_values(value, public, location, errors)
    return value


def _validate_plugin(plugin: Any, errors: list[str]) -> None:
    if not isinstance(plugin, dict):
        errors.append("plugin 必须包含 name 与 version")
        return
    try:
        validate_plugin_name(plugin.get("name"))
    except (TypeError, ValueError, AttributeError):
        errors.append("plugin.name 无效")
    try:
        Version(plugin.get("version", ""))
    except (TypeError, InvalidVersion):
        errors.append("plugin.version 无效")


def _validate_actions(actions: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for name, action in actions.items():
        permission = action.get("permission")
        if not isinstance(permission, str) or permission not in _PERMISSIONS:
            errors.append(f"actions.{name}.permission 必须为 read、operate 或 manage")
        for key in ("input_schema", "output_schema"):
            _validate_schema(action.get(key), f"actions.{name}.{key}", errors)


def _validate_resource_actions(
    resource: dict[str, Any], actions: dict[str, dict[str, Any]], location: str, errors: list[str]
) -> None:
    reference = resource.get("list_action")
    listing = actions.get(reference) if isinstance(reference, str) else None
    if listing is None or listing.get("permission") != "read":
        errors.append(f"{location}.list_action 必须引用 read 动作")
    for key in ("create_action", "delete_action"):
        reference = resource.get(key)
        if reference is None:
            continue
        if not isinstance(reference, str) or reference not in actions:
            errors.append(f"{location}.{key} 引用了不存在的动作")
            continue
        if actions[reference].get("permission") == "read":
            errors.append(f"{location}.{key} 必须引用写动作")


def _validate_resource_columns(columns: Any, location: str, errors: list[str]) -> None:
    if not isinstance(columns, list) or not columns:
        errors.append(f"{location}.columns 必须是非空列表")
        return
    keys = [item.get("key") for item in columns if isinstance(item, dict)]
    invalid_keys = len(keys) != len(columns) or any(not isinstance(key, str) or not key for key in keys)
    if invalid_keys:
        errors.append(f"{location}.columns 中的 key 无效")
        return
    if len(set(keys)) != len(keys):
        errors.append(f"{location}.columns 存在重复 key")


def _validate_resources(
    resources: dict[str, dict[str, Any]], actions: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    for name, resource in resources.items():
        location = f"resources.{name}"
        _validate_resource_actions(resource, actions, location, errors)
        _validate_resource_columns(resource.get("columns"), location, errors)


def _valid_anchor(anchor: Any) -> bool:
    if not isinstance(anchor, str):
        return False
    return bool(_ID.fullmatch(anchor)) and "." not in anchor


def _validate_view_anchors(name: str, anchors: Any, errors: list[str]) -> list[str] | None:
    valid_anchors = isinstance(anchors, list) and all(_valid_anchor(anchor) for anchor in anchors)
    if "." in name or not valid_anchors:
        errors.append(f"views.{name}.anchors 必须是无点号的稳定 ID 列表")
        return None
    if len(set(anchors)) != len(anchors):
        errors.append(f"views.{name}.anchors 不能重复")
    return anchors


def _validate_views(views: dict[str, dict[str, Any]], errors: list[str]) -> set[str]:
    targets: set[str] = set()
    for name, view in views.items():
        if not isinstance(view.get("title"), str) or not view["title"].strip():
            errors.append(f"views.{name}.title 不能为空")
        try:
            validate_view_entry(view.get("entry"))
        except ValueError:
            errors.append(f"views.{name}.entry 必须是包内 HTML 路径")
        anchors = _validate_view_anchors(name, view.get("anchors"), errors)
        if anchors is None:
            continue
        targets.update(f"view.{name}.{anchor}" for anchor in anchors)
    return targets


def _validate_guide_step(step: Any, location: str, targets: set[str], errors: list[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{location} 必须是对象")
        return
    target = step.get("target")
    if not isinstance(target, str) or target not in targets:
        errors.append(f"{location}.target 无效")
    if not isinstance(step.get("text"), str) or not step["text"].strip():
        errors.append(f"{location}.text 不能为空")
    if "chapter" in step and (not isinstance(step["chapter"], str) or not step["chapter"].strip()):
        errors.append(f"{location}.chapter 不能为空")
    if "example" in step and not isinstance(step["example"], dict):
        errors.append(f"{location}.example 必须是对象")
    if "command" in step:
        errors.extend(guide_command_errors(step["command"], f"{location}.command"))
    errors.extend(guide_form_errors(step, location))


def _validate_guide_demo(demo: Any, location: str, actions: dict[str, dict[str, Any]], errors: list[str]) -> None:
    if demo is None:
        return
    if not isinstance(demo, dict) or set(demo) - {"actions", "config"}:
        errors.append(f"{location}.demo 必须是 actions/config 合成数据")
        return
    if not all(isinstance(demo.get(key, {}), dict) for key in ("actions", "config")):
        errors.append(f"{location}.demo 必须是 actions/config 合成数据")
        return
    if any(action not in actions for action in demo.get("actions", {})):
        errors.append(f"{location}.demo 引用了不存在的动作")


def _validate_guide_completion(
    completion: Any, location: str, actions: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    if completion is None:
        return
    action = actions.get(completion) if isinstance(completion, str) else None
    if action is None or action.get("permission") != "read":
        errors.append(f"{location}.completion_action 必须引用 read 动作")


def _validate_guides(
    guides: dict[str, dict[str, Any]], actions: dict[str, dict[str, Any]], targets: set[str], errors: list[str]
) -> None:
    for name, guide in guides.items():
        location = f"guides.{name}"
        steps = guide.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{location}.steps 必须是非空列表")
            continue
        for index, step in enumerate(steps):
            _validate_guide_step(step, f"{location}.steps[{index}]", targets, errors)
        _validate_guide_demo(guide.get("demo"), location, actions, errors)
        _validate_guide_completion(guide.get("completion_action"), location, actions, errors)


def validate_contract(document: Any) -> list[str]:
    """返回可公开的诊断；错误文本仅包含字段位置，不包含输入值。"""
    if not isinstance(document, dict):
        return ["契约必须是 JSON 对象"]
    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return ["契约必须包含有限、可序列化的 JSON 值"]
    errors: list[str] = []
    if set(document) - {"schema_version", "plugin", "config", "actions", "resources", "guides", "views"}:
        errors.append("契约含未知字段")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        errors.append("schema_version 必须为整数 1")
    _validate_plugin(document.get("plugin"), errors)
    config = _validate_schema(document.get("config"), "config", errors)
    actions = _entries(document, "actions", errors)
    resources = _entries(document, "resources", errors)
    guides = _entries(document, "guides", errors)
    views = _entries(document, "views", errors)
    _validate_actions(actions, errors)
    _validate_resources(resources, actions, errors)
    targets = {f"config.{path}" for path in schema_field_paths(config)}
    if config is not None:
        targets.add("config")
    targets.update(f"action.{name}" for name in actions)
    targets.update(f"resource.{name}" for name in resources)
    targets.update(_validate_views(views, errors))
    _validate_guides(guides, actions, targets, errors)
    return errors
