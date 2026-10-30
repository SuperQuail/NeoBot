"""配置 schema 的类型内省、字符串转换与严格校验。"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, SecretBytes, SecretStr

from neobot_app.config.loader.converter import _validate_type
from neobot_app.config.model_params import extra_body_reserved_keys

#: Union 的两种表现：typing.Union（Optional[int]）与 PEP 604（int | None）
_UNION_ORIGINS = (Union, UnionType)


def _type_name(field_type: Any) -> str:
    origin = get_origin(field_type)
    if origin in _UNION_ORIGINS:
        args = [item for item in get_args(field_type) if item is not type(None)]
        if args:
            return _type_name(args[0])
        return "any"
    if origin in (list, dict):
        return origin.__name__
    if field_type in (int, float, bool, str):
        return field_type.__name__
    if is_dataclass(field_type):
        return "model"
    return "any"


def _is_optional(field_type: Any) -> bool:
    return get_origin(field_type) in _UNION_ORIGINS and type(None) in get_args(field_type)


def _inner_types(field_type: Any) -> tuple[Any, ...]:
    if get_origin(field_type) in _UNION_ORIGINS:
        return tuple(item for item in get_args(field_type) if item is not type(None))
    return (field_type,)


def _default_of(field_obj: Any) -> Any:
    if field_obj.default is not MISSING:
        return field_obj.default
    if field_obj.default_factory is not MISSING:  # type: ignore[comparison-overlap]
        try:
            return field_obj.default_factory()
        except Exception:
            return None
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (SecretStr, SecretBytes)):
        return "**********" if value.get_secret_value() else ""
    if isinstance(value, BaseModel):
        # 保留模型字段结构，后续脱敏才能识别嵌套密钥，禁止退化成含明文的 repr。
        return _jsonable(value.model_dump())
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _matches(value: Any, expected: Any) -> bool:
    if expected is Any or expected is None:
        return True
    origin = get_origin(expected)
    if origin in _UNION_ORIGINS:
        return any(_matches(value, item) for item in _inner_types(expected))
    if origin is list:
        if not isinstance(value, list):
            return False
        args = get_args(expected)
        if not args:
            return True
        return all(_matches(item, args[0]) for item in value)
    if origin is dict:
        if not isinstance(value, dict):
            return False
        args = get_args(expected)
        if len(args) != 2:
            return True
        return all(_matches(key, args[0]) and _matches(item, args[1]) for key, item in value.items())
    if is_dataclass(expected):
        return isinstance(value, dict)
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected is str:
        return isinstance(value, str)
    if expected is type(None):
        return value is None
    try:
        return isinstance(value, expected)
    except TypeError:
        return True


def _resolve_actual_schema(declared: Any, data: Any) -> Any:
    """声明类型是 dataclass 时，按数据里出现的额外字段推断真实子类。

    例如 settings 声明为 ModelSettings，实际可能是 DeepSeekModelSettings，
    否则子类专属字段会被误判为未知配置项。
    """
    if not is_dataclass(declared) or not isinstance(data, dict):
        return declared
    base_names = {item.name for item in fields(declared)}
    extra_keys = set(data) - base_names
    if not extra_keys:
        return declared
    for subclass in declared.__subclasses__():
        subclass_extra = {item.name for item in fields(subclass)} - base_names
        if extra_keys & subclass_extra:
            return _resolve_actual_schema(subclass, data)
    return declared


_COERCIBLE_TYPES = (int, float, bool, str)


def _coerce_leaf(value: Any, target: Any) -> Any:
    """把字符串值按声明类型转换；转不了就原样返回，交给校验定位报错。"""
    if not isinstance(value, str) or target not in _COERCIBLE_TYPES:
        return value
    valid, converted = _validate_type(value, target)
    return converted if valid else value


def _coerce_payload(schema: type, data: Any) -> Any:
    """把面板回传的字符串值转成声明类型（只转已存在的值，不补默认值、不删未知键）。

    前端表单的输入框一律回传字符串（「0.5」）：保存与校验必须在同一处转换，
    否则会出现「校验通过、保存 400」。转换失败的值原样保留，由 ``_validate_payload``
    指出具体路径。返回新 dict，调用方必须用返回值落盘。
    """
    if not is_dataclass(schema) or not isinstance(data, dict):
        return data
    coerced = dict(data)
    for field_obj in fields(schema):
        if field_obj.name not in coerced:
            continue
        raw = coerced[field_obj.name]
        inner = _inner_types(field_obj.type)
        target = inner[0] if inner else field_obj.type
        if is_dataclass(target):
            coerced[field_obj.name] = _coerce_payload(_resolve_actual_schema(target, raw), raw)
        elif get_origin(target) is list and isinstance(raw, list):
            args = get_args(target)
            element = args[0] if args else None
            if is_dataclass(element):
                coerced[field_obj.name] = [_coerce_payload(element, item) for item in raw]
            elif element in _COERCIBLE_TYPES:
                coerced[field_obj.name] = [_coerce_leaf(item, element) for item in raw]
        elif get_origin(target) is dict and isinstance(raw, dict):
            args = get_args(target)
            if len(args) == 2 and args[1] in _COERCIBLE_TYPES:
                coerced[field_obj.name] = {key: _coerce_leaf(item, args[1]) for key, item in raw.items()}
        else:
            coerced[field_obj.name] = _coerce_leaf(raw, target)
    return coerced


def _validate_payload(schema: type, data: Any, path: str, errors: list[dict[str, str]]) -> None:
    """严格校验配置字典：类型不匹配立即记录错误（不会静默回退默认值）。"""
    if not is_dataclass(schema):
        return
    if not isinstance(data, dict):
        errors.append({"path": path, "message": f"应为表（table），实际为 {type(data).__name__}"})
        return
    known = {item.name for item in fields(schema)}
    for key in data:
        if key not in known:
            errors.append({"path": f"{path}.{key}" if path else str(key), "message": "未知配置项"})
    for field_obj in fields(schema):
        if field_obj.name not in data:
            continue
        raw = data[field_obj.name]
        field_path = f"{path}.{field_obj.name}" if path else field_obj.name
        field_type = field_obj.type
        if raw is None and _is_optional(field_type):
            continue
        if field_obj.name == "extra_body" and isinstance(raw, dict):
            # spec(4) Part B：__ 前缀是内部键命名空间，用户自定义参数不得占用
            reserved = extra_body_reserved_keys(raw)
            if reserved:
                errors.append(
                    {
                        "path": field_path,
                        "message": "自定义参数不得使用 __ 开头（内部命名空间）: " + "、".join(reserved),
                    }
                )
        inner = _inner_types(field_type)
        if not inner:
            continue
        target = inner[0]
        if is_dataclass(target):
            _validate_payload(_resolve_actual_schema(target, raw), raw, field_path, errors)
            continue
        if get_origin(target) is list:
            if not isinstance(raw, list):
                errors.append({"path": field_path, "message": "应为数组"})
                continue
            args = get_args(target)
            if args and is_dataclass(args[0]):
                for index, item in enumerate(raw):
                    _validate_payload(args[0], item, f"{field_path}[{index}]", errors)
                continue
            if args:
                for index, item in enumerate(raw):
                    if not _matches(item, args[0]):
                        errors.append(
                            {
                                "path": f"{field_path}[{index}]",
                                "message": (f"类型应为 {_type_name(args[0])}，实际为 {type(item).__name__}"),
                            }
                        )
            continue
        if get_origin(target) is dict:
            # 只说「类型应为 dict，实际为 dict」等于没报：容器对得上、里面某个键
            # 的类型不对，必须指到那个键。
            if not isinstance(raw, dict):
                errors.append({"path": field_path, "message": f"应为表（table），实际为 {type(raw).__name__}"})
                continue
            args = get_args(target)
            if len(args) == 2:
                for key, item in raw.items():
                    item_path = f"{field_path}.{key}"
                    if not _matches(key, args[0]):
                        errors.append(
                            {
                                "path": item_path,
                                "message": (f"键类型应为 {_type_name(args[0])}，实际为 {type(key).__name__}"),
                            }
                        )
                    if not _matches(item, args[1]):
                        errors.append(
                            {
                                "path": item_path,
                                "message": (f"类型应为 {_type_name(args[1])}，实际为 {type(item).__name__}"),
                            }
                        )
            continue
        if not _matches(raw, target):
            errors.append(
                {
                    "path": field_path,
                    "message": f"类型应为 {_type_name(target)}，实际为 {type(raw).__name__}",
                }
            )
