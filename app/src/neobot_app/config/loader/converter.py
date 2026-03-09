"""配置转换工具"""

import dataclasses
from dataclasses import MISSING, fields, is_dataclass
from typing import Any, TypeVar, Union, get_args, get_origin

import tomlkit
from tomlkit.items import Table

from neobot_app.utils.logger import get_module_logger

T = TypeVar("T")
logger = get_module_logger("config_converter")


def _validate_type(value: Any, expected_type: Any) -> tuple[bool, Any]:
    """验证值是否与预期类型匹配，如果不匹配则尝试转换"""
    # 处理Optional类型
    origin = get_origin(expected_type)
    if origin is type(None) | type:  # Union type
        inner_types = [t for t in get_args(expected_type) if t is not type(None)]
        if len(inner_types) == 1:
            expected_type = inner_types[0]
        else:
            for inner_type in inner_types:
                valid, converted = _validate_type(value, inner_type)
                if valid:
                    return True, converted
            return False, value

    # 处理dataclass类型
    if is_dataclass(expected_type):
        if isinstance(value, dict):
            try:
                return True, dict_to_dataclass(value, expected_type)
            except Exception:
                return False, value
        elif is_dataclass(type(value)):
            return True, value
        return False, value

    # Any类型接受所有值
    if expected_type is Any:
        return True, value

    # 尝试直接类型检查
    try:
        if isinstance(value, expected_type):
            return True, value
    except TypeError:
        pass

    # 类型转换
    try:
        if expected_type is int and isinstance(value, (int, float, str)):
            converted = int(value)
            if isinstance(value, float) and abs(converted - value) > 0.0001:
                logger.warning(f"浮点数 {value} 转换为整数 {converted} 可能丢失精度")
            return True, converted
        elif expected_type is float and isinstance(value, (int, float, str)):
            return True, float(value)
        elif expected_type is bool and isinstance(value, (bool, int, str)):
            if isinstance(value, str):
                lower_val = value.lower()
                if lower_val in ("true", "1", "yes", "on"):
                    return True, True
                elif lower_val in ("false", "0", "no", "off"):
                    return True, False
            elif isinstance(value, int):
                return True, bool(value)
        elif expected_type is str:
            return True, str(value)
    except (ValueError, TypeError):
        pass

    return False, value


def dict_to_dataclass(data: dict, schema: type[T]) -> T:
    """递归将字典转换为dataclass，并进行类型验证"""
    if not is_dataclass(schema):
        return data  # type: ignore[return-value]

    kwargs = {}
    for field in fields(schema):
        field_name = field.name
        raw_value = data.get(field_name)

        # 验证和转换值
        if raw_value is not None:
            valid, validated_value = _validate_type(raw_value, field.type)
            value = validated_value if valid else None
            if not valid:
                logger.warning(
                    f"配置项 '{field_name}' 的类型不匹配: "
                    f"期望 {field.type}, 实际 {type(raw_value).__name__}, "
                    f"值: {repr(raw_value)}. 将视为缺失项并使用默认值"
                )
        else:
            value = None

        # 处理嵌套dataclass
        if is_dataclass(field.type) and value is not None:
            if isinstance(value, dict):
                value = dict_to_dataclass(value, field.type)
            elif not is_dataclass(type(value)):
                logger.warning(
                    f"嵌套配置项 '{field_name}' 的类型不匹配: "
                    f"期望 {field.type}, 实际 {type(value).__name__}"
                )
                value = None

        # 使用默认值
        if value is None:
            if field.default is not MISSING:
                value = field.default
            elif field.default_factory is not MISSING:
                value = field.default_factory()

        kwargs[field_name] = value

    return schema(**kwargs)


def dataclass_to_toml(
    schema: type[T],
    existing_data: dict[Any, Any] | None = None,
    is_root: bool = True,
) -> tuple[tomlkit.TOMLDocument | Table | None, list[Any], list[Any]]:
    """将dataclass schema转换为toml文档，并与现有数据比较"""
    if not is_dataclass(schema):
        return None, [], []

    # 创建文档或表格
    if is_root:
        doc = tomlkit.document()
        doc.add(tomlkit.comment("警告:此文件由程序自动生成和维护"))
        doc.add(tomlkit.comment("所有除了键值的内容（包括注释）都会在重新执行程序时丢失"))
        doc.add(tomlkit.comment("如需更改配置项/注释,请修改app/src/app/config/bot_config.py文件"))
        doc.add(tomlkit.comment("格式损坏的文件会被覆盖,data/config_backup下会存储最多十五个备份,如果意外损坏导致文件被覆盖,可自行提取备份"))
        doc.add(tomlkit.nl())
    else:
        doc = tomlkit.table()

    missing_required: list[Any] = []
    missing_optional: list[Any] = []

    for field in fields(schema):
        field_name = field.name
        description = field.metadata.get("description", "")
        field_type = field.type

        optional = get_origin(field_type) is Union and type(None) in get_args(
            field_type
        )
        required = not optional

        existing_value = None
        raw_value = None
        if existing_data is not None and field_name in existing_data:
            raw_value = existing_data.get(field_name)
            if raw_value is not None:
                valid, validated_value = _validate_type(raw_value, field_type)
                if valid:
                    existing_value = validated_value
                else:
                    logger.warning(
                        f"配置项 '{field_name}' 的类型不匹配: "
                        f"期望 {field_type}, 实际 {type(raw_value).__name__}, "
                        f"值: {repr(raw_value)}. 将视为缺失项"
                    )

        if is_dataclass(field_type):
            # 对于嵌套 dataclass，使用原始字典数据以正确检测缺失项
            nested_existing = None
            if raw_value is not None and isinstance(raw_value, dict):
                nested_existing = raw_value
            nested_doc, nested_req, nested_opt = dataclass_to_toml(
                field_type, nested_existing, is_root=False  # type: ignore[arg-type]
            )

            if existing_value is None:
                has_default = (
                    field.default is not MISSING or field.default_factory is not MISSING
                )
                if required and not has_default:
                    missing_required.append(field_name)
                elif not has_default:
                    missing_optional.append(field_name)

            if nested_doc is not None:
                doc[field_name] = nested_doc
                missing_required.extend([f"{field_name}.{req}" for req in nested_req])
                missing_optional.extend([f"{field_name}.{opt}" for opt in nested_opt])
            continue

        default_value = None
        if field.default is not MISSING:
            default_value = field.default
        elif field.default_factory is not MISSING:
            try:
                default_value = field.default_factory()
            except Exception:
                default_value = None

        value_to_use = existing_value if existing_value is not None else default_value

        if existing_value is None:
            if required:
                missing_required.append(field_name)
            else:
                missing_optional.append(field_name)

        if value_to_use is not None:
            item = tomlkit.item(value_to_use)
        else:
            actual_type = field_type
            if get_origin(field_type) is Union and type(None) in get_args(field_type):
                types = [t for t in get_args(field_type) if t is not type(None)]
                if types:
                    actual_type = types[0]

            placeholder = (
                0
                if actual_type is int
                else 0.0
                if actual_type is float
                else False
                if actual_type is bool
                else ""
            )
            item = tomlkit.item(placeholder)

        required_text = "[必须项]" if required else "[可选项]"
        if description and item is not None and hasattr(item, "comment"):
            item.comment(f"{description} {required_text}")
        doc[field_name] = item

    return doc, missing_required, missing_optional
