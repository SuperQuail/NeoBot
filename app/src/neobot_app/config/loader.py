import dataclasses
import datetime
import inspect
import os
import re
import shutil
import sys
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

import tomlkit

from neobot_app.config.bot_config import BotConfig
from neobot_app.config.env_config import EnvConfig
from neobot_app.utils.logger import get_module_logger

T = TypeVar("T")

logger = get_module_logger("config_loader")

# 项目根目录（相对于当前配置文件的父级的父级的父级）
HOME = Path(__file__).parent.parent.parent.parent.parent

# 配置文件路径
env_path = HOME / ".env"
config_path = HOME / "data" / "config.toml"
config_backup_path = HOME / "data" / "config_backup"

# 确保data目录存在
config_path.parent.mkdir(parents=True, exist_ok=True)
# 确保备份目录存在
config_backup_path.mkdir(parents=True, exist_ok=True)


def generate_env():
    logger.info("尝试生成环境变量模板...")
    fields = EnvConfig.__dataclass_fields__
    lines = []
    for field_name, field_obj in fields.items():
        # 获取字段类型
        field_type = field_obj.type
        # 判断是否为 Optional
        optional = get_origin(field_type) is Union and type(None) in get_args(
            field_type
        )
        required = not optional
        # 获取描述
        description = field_obj.metadata.get("description", "")
        # 获取默认值
        default = field_obj.default if field_obj.default is not MISSING else None
        # 环境变量名
        env_key = field_name.upper()
        # 默认值字符串
        if default is None or default is MISSING:
            default_str = ""
        else:
            default_str = str(default)
        # 构建行
        line = f"#{description} [{'必须项' if required else '非必须项'}]\n{env_key}={default_str}"
        lines.append(line)

    # 写入文件
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"环境变量模板已生成: {env_path}")
    except Exception as e:
        logger.error(f"生成环境变量模板失败: {e}")


def load_env():
    logger.info("尝试加载环境变量...")
    if env_path.exists():
        logger.info(f"环境变量文件 {env_path} 存在，开始加载...")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                key, value = line.split("=", 1)
                os.environ[key] = value
        logger.info(f"环境变量文件 {env_path} 加载完毕")
    else:
        logger.info("环境变量文件不存在")
        generate_env()
        logger.info("请手动填写环境变量文件再重启")


def _validate_type(value: Any, expected_type: Type) -> Tuple[bool, Any]:
    """
    验证值是否与预期类型匹配，如果不匹配则尝试转换

    返回: (是否有效, 转换后的值或原始值)
    """
    # 处理 Optional 类型
    origin = get_origin(expected_type)
    if origin is Union and type(None) in get_args(expected_type):
        # 提取非 None 类型
        inner_types = [t for t in get_args(expected_type) if t is not type(None)]
        if len(inner_types) == 1:
            expected_type = inner_types[0]
        else:
            # 多个非 None 类型，检查是否匹配任何一个
            for inner_type in inner_types:
                valid, converted = _validate_type(value, inner_type)
                if valid:
                    return True, converted
            return False, value

    # 处理嵌套 dataclass
    if is_dataclass(expected_type):
        if isinstance(value, dict):
            # 递归验证嵌套字典
            try:
                # 尝试转换为 dataclass，会在递归中验证类型
                return True, _dict_to_dataclass(value, expected_type)
            except Exception:
                return False, value
        elif isinstance(value, expected_type):
            # 值已经是正确的 dataclass 类型
            return True, value
        else:
            return False, value

    # 基本类型检查
    if expected_type is Any:
        return True, value

    # 类型匹配检查
    if isinstance(value, expected_type):
        return True, value

    # 尝试类型转换（例如 int -> float, str -> int 等）
    try:
        if expected_type is int and isinstance(value, (int, float, str)):
            converted = int(value)
            # 检查是否丢失精度（例如 3.14 -> 3 可以接受，但应该警告）
            if isinstance(value, float) and abs(converted - value) > 0.0001:
                logger.warning(f"浮点数 {value} 转换为整数 {converted} 可能丢失精度")
            return True, converted
        elif expected_type is float and isinstance(value, (int, float, str)):
            converted = float(value)
            return True, converted
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


def _dict_to_dataclass(data: dict, schema: Type[T]) -> T:
    """递归将字典转换为 dataclass，并进行类型验证"""
    if not is_dataclass(schema):
        return data
    kwargs = {}
    for field in fields(schema):
        field_name = field.name
        raw_value = data.get(field_name)

        # 如果原始值存在，进行类型验证
        if raw_value is not None:
            valid, validated_value = _validate_type(raw_value, field.type)
            if not valid:
                logger.warning(
                    f"配置项 '{field_name}' 的类型不匹配: "
                    f"期望 {field.type}, 实际 {type(raw_value).__name__}, "
                    f"值: {repr(raw_value)}. 将视为缺失项并使用默认值"
                )
                # 视为缺失项，使用默认值
                validated_value = None
            else:
                value = validated_value
        else:
            value = None

        # 处理嵌套dataclass
        if is_dataclass(field.type) and value is not None:
            if isinstance(value, dict):
                # 如果是字典，转换为 dataclass
                value = _dict_to_dataclass(value, field.type)
            elif not isinstance(value, field.type):
                # 如果既不是字典也不是正确的类型，视为无效
                logger.warning(
                    f"嵌套配置项 '{field_name}' 的类型不匹配: "
                    f"期望 {field.type}, 实际 {type(value).__name__}"
                )
                value = None

        # 如果值为None，尝试使用默认值
        if value is None:
            if field.default is not MISSING:
                value = field.default
            elif field.default_factory is not MISSING:
                value = field.default_factory()

        kwargs[field_name] = value
    return schema(**kwargs)


def _dataclass_to_toml(
    schema: Type[T], existing_data: dict = None, is_root: bool = True
) -> tuple[tomlkit.TOMLDocument, list, list]:
    """
    将dataclass schema转换为toml文档，并与现有数据比较，返回缺失的必须项和非必须项

    参数:
        schema: dataclass类型
        existing_data: 现有数据字典
        is_root: 是否为根文档（添加文件头注释）

    返回值: (toml_document, missing_required, missing_optional)
    """
    if not is_dataclass(schema):
        return None, [], []

    # 创建文档或表
    if is_root:
        doc = tomlkit.document()
        # 添加文件头注释
        doc.add(tomlkit.comment("警告:此文件由程序自动生成和维护"))
        doc.add(
            tomlkit.comment("所有除了键值的内容（包括注释）都会在重新执行程序时丢失")
        )
        doc.add(
            tomlkit.comment(
                "如需更改配置项/注释,请修改app/src/app/config/bot_config.py文件"
            )
        )
        doc.add(
            tomlkit.comment(
                "格式损坏的文件会被覆盖,data/config_backup下会存储最多十五个备份,如果意外损坏导致文件被覆盖,可自行提取备份"
            )
        )
        doc.add(tomlkit.nl())
    else:
        doc = tomlkit.table()

    missing_required = []
    missing_optional = []

    for field in fields(schema):
        field_name = field.name
        description = field.metadata.get("description", "")
        field_type = field.type

        # 判断是否为Optional
        optional = get_origin(field_type) is Union and type(None) in get_args(
            field_type
        )
        required = not optional

        # 获取现有值并进行类型验证
        existing_value = None
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
                    # 视为缺失项
                    existing_value = None
            else:
                existing_value = None

        # 处理嵌套dataclass
        if is_dataclass(field_type):
            # 对于嵌套dataclass，递归处理（不是根文档）
            nested_existing = None
            if existing_value is not None:
                # 如果 existing_value 已经是验证后的 dataclass 实例，需要转换为字典
                if is_dataclass(type(existing_value)):
                    # 将 dataclass 实例转换为字典以便递归处理
                    nested_existing = dataclasses.asdict(existing_value)
                elif isinstance(existing_value, dict):
                    nested_existing = existing_value
            nested_doc, nested_req, nested_opt = _dataclass_to_toml(
                field_type, nested_existing, is_root=False
            )

            # 记录当前字段的缺失状态（如果整个嵌套表缺失）
            if existing_value is None:
                # 检查是否有默认值或默认工厂
                has_default = (
                    field.default is not MISSING or field.default_factory is not MISSING
                )
                if required and not has_default:
                    missing_required.append(field_name)
                elif not has_default:
                    missing_optional.append(field_name)

            if nested_doc is not None:
                doc[field_name] = nested_doc
                # 添加嵌套字段的缺失项（带前缀）
                missing_required.extend([f"{field_name}.{req}" for req in nested_req])
                missing_optional.extend([f"{field_name}.{opt}" for opt in nested_opt])
            continue

        # 非嵌套字段（基本类型）
        # 检查是否有默认值
        default_value = None
        if field.default is not MISSING:
            default_value = field.default
        elif field.default_factory is not MISSING:
            # 对于基本类型，尝试调用默认工厂
            try:
                default_value = field.default_factory()
            except Exception:
                # 如果调用失败（例如需要参数的dataclass），则使用None
                default_value = None

        # 确定要使用的值
        value_to_use = existing_value if existing_value is not None else default_value

        # 记录缺失项
        if existing_value is None:
            if required and default_value is None:
                missing_required.append(field_name)
            elif default_value is None:
                missing_optional.append(field_name)

        # 添加到文档并添加注释
        if value_to_use is not None:
            # 根据类型显式创建 tomlkit 项目
            item = None
            if isinstance(value_to_use, bool):
                item = tomlkit.item(value_to_use)
            elif isinstance(value_to_use, int):
                item = tomlkit.item(value_to_use)
            elif isinstance(value_to_use, float):
                item = tomlkit.item(value_to_use)
            elif isinstance(value_to_use, str):
                item = tomlkit.item(value_to_use)
            else:
                # 其他类型使用通用方法
                item = tomlkit.item(value_to_use)

            # 添加注释（包括必填/可选标记）
            if required:
                required_text = "[必须项]"
            else:
                required_text = "[可选项]"
            if description and item is not None and hasattr(item, "comment"):
                text = f"{description} {required_text}"
                item.comment(text)
            doc[field_name] = item
        else:
            # 如果没有值，根据类型提供占位符值（TOML 不支持 null）
            # 获取实际类型（处理 Optional）
            actual_type = field_type
            if get_origin(field_type) is Union and type(None) in get_args(field_type):
                # 提取非 None 类型
                types = [t for t in get_args(field_type) if t is not type(None)]
                if types:
                    actual_type = types[0]

            # 根据类型设置占位符
            placeholder = None
            if actual_type is int:
                placeholder = 0
            elif actual_type is str:
                placeholder = ""
            elif actual_type is bool:
                placeholder = False
            elif actual_type is float:
                placeholder = 0.0
            else:
                # 未知类型，使用空字符串
                placeholder = ""

            # 创建带注释的占位符项
            item = None
            if isinstance(placeholder, bool):
                item = tomlkit.item(placeholder)
            elif isinstance(placeholder, int):
                item = tomlkit.item(placeholder)
            elif isinstance(placeholder, float):
                item = tomlkit.item(placeholder)
            elif isinstance(placeholder, str):
                item = tomlkit.item(placeholder)
            else:
                item = tomlkit.item(placeholder)
            if required:
                required_text = "[必须项]"
            else:
                required_text = "[可选项]"
            if description and item is not None and hasattr(item, "comment"):
                text = f"{description} {required_text}"
                item.comment(text)
            doc[field_name] = item

    return doc, missing_required, missing_optional


def backup_config_file(
    file_path: Path, backup_dir: Path, max_backups: int = 15
) -> None:
    """
    备份配置文件到备份目录，保留指定数量的最新备份

    参数:
        file_path: 原始配置文件路径
        backup_dir: 备份目录
        max_backups: 最大备份数量，默认15
    """
    if not file_path.exists():
        logger.info(f"配置文件不存在，无需备份: {file_path}")
        return

    # 生成备份文件名（使用时间戳）
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"config_{timestamp}.toml"
    backup_path = backup_dir / backup_name

    try:
        # 复制文件
        shutil.copy2(file_path, backup_path)
        logger.info(f"配置文件已备份到: {backup_path}")
    except Exception as e:
        logger.error(f"备份配置文件失败: {e}")
        return

    # 清理旧备份，只保留最新的 max_backups 个
    try:
        # 获取备份目录下所有备份文件
        backup_files = []
        pattern = re.compile(r"^config_\d{8}_\d{6}\.toml$")
        for file in backup_dir.iterdir():
            if file.is_file() and pattern.match(file.name):
                backup_files.append(file)

        # 按修改时间排序（最老的在前面）
        backup_files.sort(key=lambda x: x.stat().st_mtime)

        # 如果备份数量超过限制，删除最老的
        if len(backup_files) > max_backups:
            files_to_delete = backup_files[: len(backup_files) - max_backups]
            for old_file in files_to_delete:
                old_file.unlink()
                logger.info(f"删除旧备份文件: {old_file}")
    except Exception as e:
        logger.error(f"清理旧备份失败: {e}")


def load_config(file_path: Path, schema: Type[T]) -> T:
    """
    加载配置文件，如果不存在则生成，如果存在则检查并补全缺失项

    参数:
        file_path: 配置文件路径
        schema: dataclass schema类型

    返回:
        schema实例
    """
    logger.info(f"加载配置文件: {file_path}")

    existing_data = {}
    file_exists = file_path.exists()

    if file_exists:
        # 读取现有配置文件
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                existing_data = tomlkit.parse(content).unwrap()
            logger.info(f"配置文件已读取: {file_path}")
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            existing_data = {}

    # 生成toml文档并检查缺失项（根文档）
    toml_doc, missing_required, missing_optional = _dataclass_to_toml(
        schema, existing_data if file_exists else None, is_root=True
    )

    # 记录缺失项
    if missing_required:
        for field in missing_required:
            logger.error(f"缺失必须配置项: {field}")
    if missing_optional:
        for field in missing_optional:
            logger.info(f"缺失非必须配置项: {field}")

    # 备份现有配置文件（如果存在）
    if file_exists:
        backup_config_file(file_path, config_backup_path)

    # 写入配置文件（无论是否存在，都写入以确保格式一致和补全缺失项）
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(toml_doc))
        if file_exists:
            logger.info(f"配置文件已更新并补全缺失项: {file_path}")
        else:
            logger.info(f"配置文件已生成: {file_path}")
    except Exception as e:
        logger.error(f"写入配置文件失败: {e}")
        if not file_exists:
            logger.error("无法生成配置文件，程序退出")
            sys.exit(1)

    # 如果缺失必须项，退出程序
    if missing_required:
        logger.error("存在缺失的必须配置项，程序退出")
        sys.exit(1)

    # 重新读取文件并转换为dataclass
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            config_dict = tomlkit.parse(content).unwrap()
        config_obj = _dict_to_dataclass(config_dict, schema)
        logger.info("配置文件加载成功")
        return config_obj
    except Exception as e:
        logger.error(f"解析配置文件失败: {e}")
        sys.exit(1)


# 加载环境变量
load_env()
# 加载机器人配置
bot_config = load_config(config_path, BotConfig)
