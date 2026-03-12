import json
import logging
import time
from typing import Any, Type, TypeVar, Union, Dict, List, get_origin, get_args
from pydantic import BaseModel, ValidationError
from pydantic.type_adapter import TypeAdapter
from functools import lru_cache
from neobot_adapter.utils.logger import get_module_logger

logger = get_module_logger("adapter_utils_parse")
T = TypeVar('T', bound=BaseModel)

# 缓存模型的解析信息
@lru_cache(maxsize=128)
def _get_model_parser(model_type: Type[BaseModel]):
    """
    获取模型的解析信息，包括字段默认值和类型信息。
    缓存以避免重复计算。
    """
    fields_info = []
    model_fields = model_type.model_fields

    for field_name, field_info in model_fields.items():
        fields_info.append({
            'name': field_name,
            'annotation': field_info.annotation,
            'is_required': field_info.is_required(),
            'default': field_info.get_default(call_default_factory=True)
                if not field_info.is_required() else None,
            'default_factory': field_info.default_factory
                if hasattr(field_info, 'default_factory') else None
        })

    return {
        'fields': fields_info,
        'model_type': model_type
    }


@lru_cache(maxsize=256)
def _get_type_adapter(type_hint: Any) -> TypeAdapter:
    """获取或创建指定类型的 TypeAdapter 实例并缓存。"""
    return TypeAdapter(type_hint)


def safe_parse_model(data: Union[dict, str], data_type: Type[T]) -> T:
    """
    高性能解析 JSON 数据为 Pydantic 模型实例。
    优化策略：
    1. 使用 model_validate 作为主要路径（最快）
    2. 对于复杂嵌套结构，使用预缓存的 TypeAdapter
    3. 大幅减少日志开销
    4. 批量处理列表元素
    5. 避免重复的类型检查和异常捕获

    Args:
        data: 字典或 JSON 字符串
        data_type: 要解析的 Pydantic 模型类

    Returns:
        模型实例
    """
    # 极简化的日志记录，只在绝对必要时记录
    if data is None:
        return data_type()

    # 1. 快速处理字符串输入
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return data_type()

    if not isinstance(data, dict):
        return data_type()

    # 2. 首要优化路径：直接使用 model_validate（最快）
    try:
        return data_type.model_validate(data, strict=False)
    except ValidationError:
        # 验证失败，尝试第二种优化路径
        pass
    except Exception:
        return data_type()

    # 3. 第二种优化路径：使用 TypeAdapter（处理更复杂的验证错误）
    try:
        adapter = _get_type_adapter(data_type)
        return adapter.validate_python(data)
    except ValidationError:
        # 仍然失败，使用容错解析
        pass
    except Exception:
        return data_type()

    # 4. 容错解析路径（极少使用）
    return _fast_fallback_parse(data, data_type)


def _fast_fallback_parse(data: Dict[str, Any], data_type: Type[T]) -> T:
    """
    快速容错解析，针对大量数据的优化版本。
    特点：
    1. 避免日志记录
    2. 批量处理字段
    3. 预计算字段信息
    """
    # 获取缓存的模型信息
    parser_info = _get_model_parser(data_type)
    field_values = {}

    for field_info in parser_info['fields']:
        field_name = field_info['name']

        # 检查字段是否存在
        if field_name in data:
            raw_value = data[field_name]
            if raw_value is None:
                field_values[field_name] = None
            else:
                # 尝试快速解析字段值
                try:
                    field_values[field_name] = _fast_parse_value(
                        raw_value,
                        field_info['annotation']
                    )
                except Exception:
                    # 解析失败，使用默认值
                    if field_info['is_required']:
                        field_values[field_name] = None
                    else:
                        field_values[field_name] = field_info['default']
        else:
            # 字段缺失
            if field_info['is_required']:
                field_values[field_name] = None
            else:
                field_values[field_name] = field_info['default']

    # 尝试创建实例
    try:
        return data_type(**field_values)
    except Exception:
        return data_type()


def _fast_parse_value(value: Any, expected_type: Any) -> Any:
    """
    超快速解析单个值，使用极简化的类型检查和错误处理。
    优化策略：
    1. 使用本地变量缓存类型检查结果
    2. 减少函数调用
    3. 使用最快的类型判断方法
    4. 避免创建异常对象
    """
    # 快速路径1：值已经是期望类型
    if isinstance(value, expected_type):
        return value

    # 快速路径2：None 值
    if value is None:
        return None

    # 快速路径3：基本类型转换
    if expected_type is int:
        try:
            return int(value)
        except (ValueError, TypeError):
            raise
    elif expected_type is float:
        try:
            return float(value)
        except (ValueError, TypeError):
            raise
    elif expected_type is str:
        try:
            return str(value)
        except (ValueError, TypeError):
            raise
    elif expected_type is bool:
        try:
            return bool(value)
        except (ValueError, TypeError):
            raise

    # 获取类型信息（缓存结果）
    origin = get_origin(expected_type)

    # 处理列表类型（性能关键路径）
    if origin is list:
        if not isinstance(value, list):
            raise TypeError

        args = get_args(expected_type)
        if not args:
            return value

        elem_type = args[0]
        # 预分配列表大小（性能优化）
        result = [None] * len(value)
        for i, item in enumerate(value):
            try:
                result[i] = _fast_parse_value(item, elem_type)
            except Exception:
                # 保持 None，不抛出异常
                pass
        return result

    # 处理 Union 类型（包括 Optional）
    if origin is Union:
        args = get_args(expected_type)

        # 检查 None
        if value is None:
            for arg in args:
                if arg is type(None):
                    return None

        # 尝试每个非None类型
        for arg in args:
            if arg is type(None):
                continue
            try:
                return _fast_parse_value(value, arg)
            except Exception:
                continue
        raise ValueError

    # 处理 BaseModel 子类（性能优化路径）
    if isinstance(expected_type, type) and issubclass(expected_type, BaseModel):
        if not isinstance(value, dict):
            raise TypeError

        # 极速路径：直接使用 TypeAdapter（已缓存）
        try:
            adapter = _get_type_adapter(expected_type)
            return adapter.validate_python(value)
        except ValidationError:
            # 验证失败，尝试 model_validate（更宽容）
            try:
                return expected_type.model_validate(value, strict=False)
            except ValidationError:
                # 最后回退到安全解析
                return safe_parse_model(value, expected_type)

    # 其他类型：尝试 TypeAdapter
    try:
        adapter = _get_type_adapter(expected_type)
        return adapter.validate_python(value)
    except Exception:
        # 最后手段：尝试类型转换
        try:
            return expected_type(value)
        except Exception:
            raise


# 保持向后兼容的函数签名
def _parse_field(field_name: str, value: Any, expected_type: Type, data_path: str) -> Any:
    """
    兼容性函数，委托给 _fast_parse_value
    """
    try:
        return _fast_parse_value(value, expected_type)
    except Exception as e:
        raise ValueError(f"字段 '{field_name}' 解析失败: {e}")

# ------------------ 使用示例 ------------------
# from pydantic import BaseModel
# from typing import List, Optional
#
# class Address(BaseModel):
#     street: str
#     city: str
#     zipcode: Optional[str] = None
#
# class Person(BaseModel):
#     name: str
#     age: int
#     address: Address
#     emails: List[str]
#     friends: List['Person'] = []  # 自引用需要字符串标注
#     spouse: Optional['Person'] = None
#
# # 解决自引用 forward reference
# Person.model_rebuild()
# try:
#     person = safe_parse_model(Person, json_data)
#     logger.info(f"解析成功: {person}")
#
# except Exception as e:
#     logger.error(f"解析失败: {e}")
