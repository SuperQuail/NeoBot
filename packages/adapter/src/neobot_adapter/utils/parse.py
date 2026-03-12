import json
import logging
from typing import Any, Type, TypeVar, Union, get_origin, get_args
from pydantic import BaseModel, ValidationError
from neobot_adapter.utils.logger import get_module_logger

logger = get_module_logger("adapter_utils_parse")
T = TypeVar('T', bound=BaseModel)


def safe_parse_model(data: Union[dict, str],data_type: Type[T]) -> T:
    """
    将 JSON 数据（字典或字符串）安全地解析为指定的 Pydantic 模型实例。
    对于缺失或不合法的字段，会尝试使用模型定义的默认值，并记录错误日志。
    支持嵌套模型、列表、Union/Optional 等类型。

    Args:
        data_type: 要解析的 Pydantic 模型类
        data: 字典或 JSON 字符串

    Returns:
        模型实例
    """
    logger.debug(f"开始解析数据: {data}")
    if data is None:
        logger.debug("输入数据为 None，返回全默认实例")
        return data_type()

    # 1. 如果输入是字符串，先尝试解析为 JSON 字典
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}，将返回全默认实例")
            return data_type()  # 返回所有字段为默认值的实例

    if not isinstance(data, dict):
        logger.error(f"输入数据类型错误，期望 dict 或 JSON 字符串，实际为 {type(data)}，返回默认实例")
        return data_type()

    # 2. 递归解析每个字段，收集有效值
    field_values = {}
    for field_name, field_info in data_type.model_fields.items():
        # 从输入数据中获取该字段的值，若不存在则为 None（但需区分缺失和显式 None）
        raw_value = data.get(field_name, None)  # 注意：如果字段存在但值为 None，会返回 None
        has_key = field_name in data

        # 如果数据中缺少该字段，尝试使用默认值
        if not has_key:
            # 字段是否有默认值？
            if field_info.is_required():
                # 必需字段且缺失：无法自动处理，记录错误并尝试用类型的默认值（如 None 或空值）填充
                logger.error(f"字段 '{field_name}' 缺失且无默认值，将使用 None（可能导致后续错误）")
                field_values[field_name] = None
            else:
                # 有默认值，直接使用默认值（后续不再处理）
                default_value = field_info.get_default(call_default_factory=True)
                field_values[field_name] = default_value
            continue

        # 数据中存在该字段，递归解析其值
        try:
            parsed_value = _parse_field(
                field_name, raw_value, field_info.annotation, data_path=field_name
            )
            field_values[field_name] = parsed_value
        except Exception as e:
            # 解析过程中发生任何异常，回退到默认值（如果有）
            logger.debug(f"字段 '{field_name}' 解析失败: {e}，将使用默认值")
            if field_info.is_required():
                # 必需字段但解析失败：无法获得有效值，用 None 填充（可能引发后续错误）
                field_values[field_name] = None
            else:
                field_values[field_name] = field_info.get_default(call_default_factory=True)

    # 3. 使用收集到的值创建模型实例
    try:
        return data_type(**field_values)
    except Exception as e:
        logger.error(f"最终模型实例化失败: {e}，返回全默认实例")
        return data_type()


def _parse_field(field_name: str, value: Any, expected_type: Type, data_path: str) -> Any:
    """
    递归解析单个字段的值，使其符合 expected_type。
    支持嵌套模型、List[模型]、Union 等。
    """
    # 处理 None 值（如果类型允许 Optional）
    if value is None:
        # 检查 expected_type 是否为 Optional（Union 包含 None）
        origin = get_origin(expected_type)
        if origin is Union:
            args = get_args(expected_type)
            if type(None) in args:
                return None
        # 如果类型不允许 None，则抛出异常，由上层处理
        raise ValueError(f"字段 '{field_name}' 的值为 None，但类型 {expected_type} 不允许")

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    # 情况1：期望的类型是 Pydantic 模型（BaseModel 子类）
    if isinstance(expected_type, type) and issubclass(expected_type, BaseModel):
        if not isinstance(value, dict):
            raise TypeError(f"字段 '{field_name}' 期望 dict 构建模型 {expected_type.__name__}，实际得到 {type(value)}")
        # 递归解析子模型
        return safe_parse_model(value, expected_type)

    # 情况2：列表类型 List[T]
    elif origin is list:
        if not isinstance(value, list):
            raise TypeError(f"字段 '{field_name}' 期望 list，实际得到 {type(value)}")
        if args:
            elem_type = args[0]
            # 解析列表中的每个元素
            parsed_list = []
            for idx, item in enumerate(value):
                item_path = f"{data_path}[{idx}]"
                try:
                    parsed_item = _parse_field(
                        f"{field_name}[{idx}]", item, elem_type, data_path=item_path
                    )
                    parsed_list.append(parsed_item)
                except Exception as e:
                    # 列表元素解析失败：根据元素类型尝试提供默认值
                    logger.error(f"列表元素 {item_path} 解析失败: {e}，将使用 None")
                    # 简单回退为 None（可根据需要调整）
                    parsed_list.append(None)
            return parsed_list
        else:
            # 没有指定元素类型，直接返回原列表
            return value

    # 情况3：Union 类型（包括 Optional）
    elif origin is Union:
        # 尝试每个子类型，直到解析成功
        for arg in args:
            # 忽略 NoneType（已在开头处理）
            if arg is type(None):
                continue
            try:
                return _parse_field(field_name, value, arg, data_path)
            except Exception:
                continue
        # 所有类型都失败，抛出异常
        raise ValueError(f"字段 '{field_name}' 的值 {value} 无法匹配 Union 中的任何类型 {args}")

    # 情况4：其他基本类型（int, str, bool 等）
    else:
        # 尝试直接使用类型构造（例如 int(value)），如果失败则抛出异常
        try:
            # 如果 value 已经是期望类型，直接返回；否则尝试转换
            if isinstance(value, expected_type):
                return value
            return expected_type(value)
        except Exception as e:
            raise ValueError(f"字段 '{field_name}' 无法转换为 {expected_type}: {e}")


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
