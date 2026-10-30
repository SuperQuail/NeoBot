"""将插件的 Pydantic 模型映射到宿主已有控件，凭据保护沿用配置接口规则。"""

from enum import Enum
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .normalize import _MISSING, _field_input_paths, _submitted_field
from .schema import _inner_types, _jsonable, _type_name
from .secret_values import PluginSecretPolicy


def _target(annotation: Any) -> Any:
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    variants = _inner_types(annotation)
    return variants[0] if len(variants) == 1 else None


def _model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _options(annotation: Any) -> list[Any] | None:
    if get_origin(annotation) is Literal:
        return list(get_args(annotation))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [member.value for member in annotation]
    return None


def _option_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _present(value: Any) -> bool:
    if isinstance(value, (SecretStr, SecretBytes)):
        value = value.get_secret_value()
    if isinstance(value, (str, bytes)):
        return bool(value.strip())
    return value is not None and value != ""


def _constraints(field: FieldInfo) -> dict[str, Any]:
    result = {}
    names = {
        "ge": "min",
        "le": "max",
        "gt": "exclusive_min",
        "lt": "exclusive_max",
        "min_length": "min_length",
        "max_length": "max_length",
        "pattern": "pattern",
    }
    for metadata in field.metadata:
        for source, target in names.items():
            value = getattr(metadata, source, None)
            if value is not None and isinstance(value, (str, int, float)):
                result[target] = value
    return result


class _DescriptorBuilder:
    def __init__(self) -> None:
        self.policies: dict[type[BaseModel], PluginSecretPolicy] = {}

    def fields(
        self, model: type[BaseModel], values: Any, path: tuple[str | int, ...], seen: frozenset[type]
    ) -> list[dict[str, Any]]:
        data = _jsonable(values) if values is not None else {}
        data = data if isinstance(data, dict) else {}
        if model not in self.policies:
            self.policies[model] = PluginSecretPolicy(model)
        policy = self.policies[model]
        config = model.model_config
        by_alias = config.get("validate_by_alias", True)
        by_name = config.get("validate_by_name", config.get("populate_by_name", False))
        return [
            self.field(
                name,
                field,
                data,
                path,
                seen | {model},
                policy,
                input_paths=_field_input_paths(name, field, by_alias=by_alias, by_name=by_name),
                selected=_submitted_field(data, name, field, by_alias=by_alias, by_name=by_name),
                model_value=getattr(values, name, _MISSING) if isinstance(values, BaseModel) else _MISSING,
            )
            for name, field in model.model_fields.items()
        ]

    def field(
        self,
        name: str,
        field: FieldInfo,
        values: dict[str, Any],
        path: tuple[str | int, ...],
        seen: frozenset[type],
        policy: PluginSecretPolicy,
        *,
        input_paths: list[list[str | int]],
        selected: tuple[list[str | int], Any] | None,
        model_value: Any,
    ) -> dict[str, Any]:
        default = field.get_default(call_default_factory=True)
        if default is PydanticUndefined:
            default = None
        input_path, value = selected if selected is not None else (input_paths[0], default)
        if selected is None and model_value is not _MISSING:
            value = model_value
        # 保留负下标的相对语义：草稿扩容后旧描述符仍须指向同一个别名。
        form_path = [int(part) if isinstance(part, int) else part for part in input_path]
        extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
        target = _target(field.annotation)
        descriptor: dict[str, Any] = {
            "name": name,
            "path": [*path, *form_path],
            "label": field.title or name,
            "description": field.description or "",
            "required": field.is_required(),
            "default": policy.mask({name: _jsonable(default)})[name],
            "value": policy.mask({name: _jsonable(value)})[name],
            "kind": "scalar",
            "type": _type_name(target),
            "readonly": bool(field.frozen or extra.get("readonly") or extra.get("readOnly")),
            "hot_reload": True,
            "restart_reason": "",
            **_constraints(field),
        }
        if policy.sensitive((name,), _jsonable(value)):
            # 容器也可被整体标为只写，不能继续为其展开包含私密键名的子控件。
            descriptor.update(type="str", sensitive=True, has_value=_present(value), default="", value="")
            return descriptor
        # 只开放文本显示提示，不允许元数据替换类型、控件或凭据保护。
        if target is str:
            if type(extra.get("single_line")) is bool:
                descriptor["single_line"] = extra["single_line"]
            if isinstance(extra.get("placeholder"), str):
                descriptor["placeholder"] = extra["placeholder"]
        options = _options(target)
        if options is not None:
            return self.enum(descriptor, options, extra)
        field_path = (*path, *form_path)
        if _model(target) and target not in seen:
            descriptor.update(kind="group", type="model", fields=self.fields(target, value, field_path, seen))
            return descriptor
        if target is list or get_origin(target) is list:
            return self.collection(descriptor, target, value, field_path, seen)
        if target is dict or get_origin(target) is dict:
            descriptor.update(kind="dict", type="dict")
            return descriptor
        if target in (SecretStr, SecretBytes):
            descriptor["type"] = "str"
            return descriptor
        if descriptor["type"] == "any":
            # 递归模型、多分支联合和未知结构保持 JSON，不能用 String(object) 丢失信息。
            descriptor["kind"] = "json"
        return descriptor

    @staticmethod
    def enum(descriptor: dict[str, Any], options: list[Any], extra: dict[str, Any]) -> dict[str, Any]:
        if any(not isinstance(value, (str, int, float, bool, type(None))) for value in options):
            descriptor["kind"] = "json"
            return descriptor
        keys = [_option_key(value) for value in options]
        if len(set(keys)) != len(keys):
            descriptor["kind"] = "json"
            return descriptor
        descriptor.update(type="str", options=keys, option_values=dict(zip(keys, options)), options_strict=True)
        labels = extra.get("option_labels")
        if isinstance(labels, dict):
            descriptor["option_labels"] = {str(key): str(label) for key, label in labels.items()}
        return descriptor

    def collection(
        self,
        descriptor: dict[str, Any],
        annotation: Any,
        value: Any,
        path: tuple[str | int, ...],
        seen: frozenset[type],
    ) -> dict[str, Any]:
        arguments = get_args(annotation)
        element = _target(arguments[0]) if arguments else Any
        if not _model(element) or element in seen:
            if element not in (str, int, float, bool):
                descriptor.update(kind="json", type="list")
                return descriptor
            descriptor.update(kind="list", type="list", element_type=_type_name(element))
            return descriptor
        rows = value if isinstance(value, (list, tuple)) else []
        descriptor.update(
            kind="model_list",
            item_label="项",
            item_fields=self.fields(element, {}, path, seen),
            items=[
                {"index": index, "fields": self.fields(element, row, (*path, str(index)), seen)}
                for index, row in enumerate(rows)
            ],
        )
        return descriptor


def describe_pydantic_fields(model: type[BaseModel], values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """只生成声明和已脱敏的值；每次请求独立缓存模型规则，避免跨插件状态泄漏。"""
    return _DescriptorBuilder().fields(model, values, (), frozenset())
