"""把 dataclass / pydantic 配置模型转成面板可渲染的字段描述。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin

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


def describe_pydantic_model(model: Any, values: Any = None) -> list[dict[str, Any]]:
    """把 pydantic 配置模型转换为面板可渲染的字段描述（官方插件配置用）。"""
    if model is None or not hasattr(model, "model_fields"):
        return []
    from pydantic_core import PydanticUndefined

    data = dict(values or {})
    descriptors: list[dict[str, Any]] = []
    for name, info in model.model_fields.items():
        annotation = getattr(info, "annotation", None)
        # 类型必须来自注解本身：按 json-schema 名字映射会把 int/bool/float 一律
        # 退化成 str，面板就把数字当文本框渲染（静默漂移）。
        type_name = _type_name(annotation)
        default = info.get_default(call_default_factory=True)
        if default is PydanticUndefined:
            default = None
        extra = getattr(info, "json_schema_extra", None) or {}
        metadata = getattr(info, "metadata", ()) or ()
        minimum = maximum = None
        for item in metadata:
            if hasattr(item, "ge") and item.ge is not None:
                minimum = item.ge
            if hasattr(item, "le") and item.le is not None:
                maximum = item.le
        descriptor: dict[str, Any] = {
            "name": name,
            "path": [name],
            "label": str(getattr(info, "title", "") or name),
            "description": str(getattr(info, "description", "") or ""),
            "required": bool(getattr(info, "is_required", lambda: False)()),
            "default": _jsonable(default),
            "value": _jsonable(data.get(name, default)),
            "kind": "scalar",
            "type": type_name,
            "readonly": bool(isinstance(extra, dict) and extra.get("readonly")),
            "hot_reload": True,
            "restart_reason": "",
        }
        inner = _inner_types(annotation)
        target = inner[0] if inner else annotation
        if get_origin(target) is list:
            args = get_args(target)
            descriptor["kind"] = "list"
            descriptor["element_type"] = _type_name(args[0]) if args else "any"
        if minimum is not None:
            descriptor["min"] = minimum
        if maximum is not None:
            descriptor["max"] = maximum
        descriptors.append(descriptor)
    return descriptors


def _collect_scalar_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """递归收集分组内的标量字段描述（用于汇总热重载状态）。"""
    collected: list[dict[str, Any]] = []
    for field in fields:
        if field.get("kind") == "group":
            collected.extend(_collect_scalar_fields(field.get("fields") or []))
        elif field.get("kind") in {"scalar", "list", "dict"}:
            collected.append(field)
    return collected
