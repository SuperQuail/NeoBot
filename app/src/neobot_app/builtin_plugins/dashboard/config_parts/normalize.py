"""按提交时的命名与结构回填校验结果，避免保存配置时迁移别名或丢掉未知字段。"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, AliasPath, BaseModel
from pydantic.fields import FieldInfo

_MISSING = object()


def _field_input_paths(name: str, field: FieldInfo, *, by_alias: bool, by_name: bool) -> list[list[str | int]]:
    alias = field.validation_alias if field.validation_alias is not None else field.alias
    if alias is None:
        return [[name]]
    if isinstance(alias, AliasChoices):
        aliases = alias.convert_to_aliases()
    elif isinstance(alias, AliasPath):
        aliases = [alias.convert_to_aliases()]
    else:
        aliases = [[alias]]
    paths = aliases if by_alias else []
    return [*paths, [name]] if by_name and [name] not in paths else paths


def _value_at_input_path(value: Any, path: list[str | int]) -> Any:
    for part in path:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, (list, tuple)) and isinstance(part, int) and -len(value) <= part < len(value):
            value = value[part]
        else:
            return _MISSING
    return value


def _replace_input_value(value: Any, path: list[str | int], replacement: Any) -> Any:
    part, *rest = path
    result = dict(value) if isinstance(value, dict) else list(value)
    result[part] = _replace_input_value(value[part], rest, replacement) if rest else replacement
    return result


def _submitted_field(
    submitted: dict[str, Any], name: str, field: FieldInfo, *, by_alias: bool, by_name: bool
) -> tuple[list[str | int], Any] | None:
    """遵守模型的别名优先级，只选择实际参与校验的输入位置。"""
    for path in _field_input_paths(name, field, by_alias=by_alias, by_name=by_name):
        value = _value_at_input_path(submitted, path)
        if value is not _MISSING:
            return path, value
    return None


def _normalize_model_fields(submitted: dict[str, Any], validated: BaseModel) -> dict[str, Any]:
    result = dict(submitted)
    model = type(validated)
    by_alias = model.model_config.get("validate_by_alias", True)
    by_name = model.model_config.get("validate_by_name", model.model_config.get("populate_by_name", False))
    for name, field in model.model_fields.items():
        selected = _submitted_field(submitted, name, field, by_alias=by_alias, by_name=by_name)
        if selected is None:
            continue
        path, value = selected
        normalized = normalize_config_values(value, getattr(validated, name))
        result = _replace_input_value(result, path, normalized)
    return result


def _normalize_mapping(submitted: dict[str, Any], validated: dict[Any, Any]) -> dict[str, Any]:
    normalized = {str(key): value for key, value in validated.items()}
    result = dict(submitted)
    for key, value in submitted.items():
        if str(key) not in normalized:
            continue
        result[key] = normalize_config_values(value, normalized[str(key)])
    return result


def _normalize_sequence(submitted: list | tuple, validated: list | tuple) -> list:
    result = []
    for index, item in enumerate(validated):
        original = submitted[index] if index < len(submitted) else item
        result.append(normalize_config_values(original, item))
    return result


def normalize_config_values(submitted: Any, validated: Any) -> Any:
    """只更新实际提交的字段；密钥类型留给配置编辑器转换为真实 TOML 文本。"""
    if isinstance(validated, BaseModel) and type(validated).__pydantic_root_model__:
        return normalize_config_values(submitted, validated.root)
    if isinstance(validated, BaseModel) and isinstance(submitted, dict):
        return _normalize_model_fields(submitted, validated)
    if isinstance(validated, BaseModel):
        return validated.model_dump()
    if isinstance(submitted, dict) and isinstance(validated, dict):
        return _normalize_mapping(submitted, validated)
    if isinstance(submitted, (list, tuple)) and isinstance(validated, (list, tuple)):
        return _normalize_sequence(submitted, validated)
    return validated
