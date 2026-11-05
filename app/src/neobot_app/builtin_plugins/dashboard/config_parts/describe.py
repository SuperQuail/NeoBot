"""把 dataclass / pydantic 配置模型转成面板可渲染的字段描述。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from .pydantic_fields import describe_pydantic_fields
from .schema import _default_of, _inner_types, _is_optional, _jsonable, _type_name


def describe_dataclass(schema: type, instance: Any, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """把 dataclass 结构转换为前端可渲染的字段描述（含热重载标注）。"""
    from neobot_app.config.hot_reload import classify

    descriptors: list[dict[str, Any]] = []
    if not is_dataclass(schema):
        return descriptors
    for field_obj in fields(schema):
        name = field_obj.name
        description = str(field_obj.metadata.get("description", "") or "")
        field_type = field_obj.type
        value = getattr(instance, name, None) if instance is not None else None
        inner = _inner_types(field_type)
        target = inner[0] if inner else field_type
        field_path = (*path, name)
        hot_reload, restart_reason = classify(field_path)
        item: dict[str, Any] = {
            "name": name,
            "path": [*path, name],
            "label": name,
            "description": description,
            "required": not _is_optional(field_type),
            "default": _jsonable(_default_of(field_obj)),
            "value": _jsonable(value),
            "kind": "scalar",
            "type": _type_name(field_type),
            "readonly": bool(field_obj.metadata.get("readonly", False)),
            "hot_reload": hot_reload,
            "restart_reason": restart_reason,
            "hidden": bool(field_obj.metadata.get("hidden", False)),
        }
        options = field_obj.metadata.get("options")
        if isinstance(options, (list, tuple)) and options:
            item["options"] = [str(value) for value in options]
            if field_obj.metadata.get("options_strict"):
                item["options_strict"] = True
        option_labels = field_obj.metadata.get("option_labels")
        if isinstance(option_labels, dict) and option_labels:
            item["option_labels"] = {str(key): str(label) for key, label in option_labels.items()}
        # 分组下拉（推理强度按供应商分 OpenAI / Claude 两系）：形态不合法整组丢弃，
        # 免得前端拿到半截分组渲染出错。
        option_groups = field_obj.metadata.get("option_groups")
        if isinstance(option_groups, (list, tuple)):
            groups: list[dict[str, Any]] = []
            for group in option_groups:
                if not isinstance(group, dict):
                    continue
                label = group.get("label")
                group_options = group.get("options")
                if not isinstance(label, str) or not isinstance(group_options, list):
                    continue
                groups.append({"label": label, "options": [str(value) for value in group_options]})
            if groups:
                item["option_groups"] = groups
        if is_dataclass(target):
            actual_schema = target
            if is_dataclass(value) and isinstance(value, target):
                actual_schema = type(value)
            item["kind"] = "group"
            item["fields"] = describe_dataclass(actual_schema, value, (*path, name))
            scalars = _collect_scalar_fields(item["fields"])
            hot_count = sum(1 for field in scalars if field.get("hot_reload"))
            item["hot_reload"] = bool(scalars) and hot_count == len(scalars)
            item["partial_hot_reload"] = 0 < hot_count < len(scalars)
            item["hot_reload_count"] = hot_count
            item["field_count"] = len(scalars)
        elif get_origin(target) is list:
            args = get_args(target)
            element = args[0] if args else Any
            if is_dataclass(element):
                item["kind"] = "model_list"
                item["item_label"] = "项"
                item["item_fields"] = describe_dataclass(element, None, (*path, name))
                item["items"] = [
                    {
                        "index": index,
                        "fields": describe_dataclass(element, entry, (*path, name, str(index))),
                    }
                    for index, entry in enumerate(value or [])
                ]
            else:
                item["kind"] = "list"
                item["element_type"] = _type_name(element)
        elif get_origin(target) is dict:
            item["kind"] = "dict"
        descriptors.append(item)
    return descriptors


def describe_pydantic_model(
    model: type[BaseModel] | None, values: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """把插件的配置模型转换为前端字段描述，脱敏规则与原配置读写保持一致。"""
    # 旧插件可以不使用 Pydantic，此时继续使用配置文件生成的字段描述。
    if model is None or not hasattr(model, "model_fields"):
        return []
    return describe_pydantic_fields(model, values)


def _collect_scalar_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """递归收集分组内的标量字段描述（用于汇总热重载状态）。"""
    collected: list[dict[str, Any]] = []
    for field in fields:
        if field.get("kind") == "group":
            collected.extend(_collect_scalar_fields(field.get("fields") or []))
        elif field.get("kind") in {"scalar", "list", "dict"}:
            collected.append(field)
    return collected
