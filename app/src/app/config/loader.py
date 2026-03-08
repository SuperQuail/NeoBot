from pathlib import Path
from app.utils.logger import get_module_logger
from app.config.bot_config import BotConfig
from app.config.env_config import env_config
from typing import Optional, get_origin, get_args, Union
import inspect
import sys
from typing import Dict, Any
import tomlkit

logger = get_module_logger("config_loader")

env_path = Path("../../../../.env")
config_path = Path("../../../../data/config.toml")

def parse_env_file(path: Path) -> dict:
    """解析.env 文件，返回键值对字典"""
    env_dict = {}
    
    if not path.exists():
        return env_dict
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            
            # 解析键值对
            if '=' in line:
                key, value = line.split('=', 1)
                env_dict[key.strip()] = value.strip()

    return env_dict


def parse_toml_file(path: Path) -> Dict[str, Any]:
    """解析TOML文件，返回字典"""
    if not path.exists():
        return {}

    with open(path, 'rb') as f:
        try:
            return tomlkit.load(f)
        except Exception as e:
            logger.error(f"解析TOML文件失败：{e}")
            sys.exit(1)


def get_nested_value(data: Dict[str, Any], key_path: str) -> Any:
    """
    从嵌套字典中获取值，key_path为点分隔路径（如 'bot.ACCOUNT'）
    如果路径不存在则返回None
    """
    keys = key_path.split('.')
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def set_nested_value(data: Dict[str, Any], key_path: str, value: Any) -> None:
    """
    在嵌套字典中设置值，key_path为点分隔路径（如 'bot.ACCOUNT'）
    自动创建中间字典
    """
    keys = key_path.split('.')
    current = data
    for i, key in enumerate(keys[:-1]):
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def flatten_dict(data: Dict[str, Any], prefix="") -> Dict[str, Any]:
    """
    将嵌套字典扁平化为点分隔路径字典
    """
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def is_optional_type(type_hint) -> bool:
    """
    判断一个类型是否为Optional 类型
    
    Optional[T] 实际上是 Union[T, None] 的语法糖
    使用 get_origin 和 get_args 来正确检测
    """
    origin = get_origin(type_hint)
    args = get_args(type_hint)
    
    # Optional[T] 等价于 Union[T, None]
    # 所以 origin 应该是 Union，并且 args 中应该包含 type(None)
    return origin is Union and type(None) in args


def get_config_items(config_class) -> Dict[str, Dict[str, Any]]:
    """从配置类中提取配置项定义（扁平化，支持嵌套类）"""
    items = {}

    def collect_from_class(cls, prefix=""):
        for name, value in inspect.getmembers(cls):
            # 跳过内置属性
            if name.startswith('_'):
                continue

            # 如果是嵌套类，递归处理
            if inspect.isclass(value):
                # 嵌套类表示一个section，递归收集其配置项
                new_prefix = f"{prefix}.{name}" if prefix else name
                collect_from_class(value, new_prefix)
            # 检查是否是配置项（应该是字典类型且包含 type 和 description 键）
            elif isinstance(value, dict) and 'type' in value and 'description' in value:
                full_name = f"{prefix}.{name}" if prefix else name
                items[full_name] = value

    collect_from_class(config_class)
    return items


def get_nested_config_structure(config_class) -> Dict[str, Any]:
    """
    获取嵌套配置结构，返回层级字典

    Returns:
        Dict[str, Any]: 嵌套字典，结构为 {
            'sections': {
                'section_name': {
                    'description': str,  # section的描述（来自docstring）
                    'items': Dict[str, Dict[str, Any]]  # 该section下的配置项
                }
            },
            'root_items': Dict[str, Dict[str, Any]]  # 根级配置项
        }
    """
    result = {
        'sections': {},
        'root_items': {}
    }

    for name, value in inspect.getmembers(config_class):
        # 跳过内置属性
        if name.startswith('_'):
            continue

        # 如果是嵌套类，表示一个section
        if inspect.isclass(value):
            section_name = name
            section_description = inspect.getdoc(value) or ''
            section_items = {}

            # 收集该section下的配置项
            for item_name, item_value in inspect.getmembers(value):
                if item_name.startswith('_'):
                    continue
                if isinstance(item_value, dict) and 'type' in item_value and 'description' in item_value:
                    section_items[item_name] = item_value

            result['sections'][section_name] = {
                'description': section_description,
                'items': section_items
            }
        # 如果是配置项，放在根级
        elif isinstance(value, dict) and 'type' in value and 'description' in value:
            result['root_items'][name] = value

    return result


def generate_env_template():
    """根据 env_config 自动生成.env 模板文件，包含注释说明"""
    lines = []
    
    config_items = get_config_items(env_config)

    for name, config_item in config_items.items():
        description = config_item.get('description', '')
        value_type = config_item.get('type', '')
        default_value = config_item.get('value', '')

        # 添加必填/可选标记
        required_txt = ""
        if not is_optional_type(value_type):
            required_txt = ' [必须项]'
        else:
            required_txt = ' [可选项]'

        # 添加描述注释
        lines.append(f"# {description}"+required_txt)

        # 添加配置项
        lines.append(f"{name}={default_value}")

        # 空行分隔
        lines.append("")

    return "\n".join(lines)


def generate_toml_template(config_class, existing_values: Dict[str, Any] = None) -> str:
    """根据配置类自动生成TOML模板文件，包含注释说明（支持嵌套section）"""
    lines = ["# TOML 配置文件", "# 请根据实际情况填写以下配置项\n"]

    # 获取嵌套配置结构
    structure = get_nested_config_structure(config_class)
    sections = structure['sections']
    root_items = structure['root_items']

    # 处理根级配置项（如果有）
    if root_items:
        lines.append("# 根级配置项")
        for name, config_item in root_items.items():
            description = config_item.get('description', '')
            value_type = config_item.get('type', '')
            default_value = config_item.get('value', '')

            # 获取现有值（扁平路径）
            value_to_use = default_value
            if existing_values and name in existing_values:
                value_to_use = existing_values[name]

            # 格式化值
            toml_value = format_value_for_toml(value_to_use)

            # 添加注释和配置项
            required_text = " [必须项]" if not is_optional_type(value_type) else " [可选项]"
            # 注释放在同一行后方，不换行
            lines.append(f"{name} = {toml_value}  # {description}{required_text}")
        lines.append("")

    # 处理每个section
    for section_name, section_data in sections.items():
        section_description = section_data['description']
        items = section_data['items']

        # 添加section描述注释（如果非空）
        if section_description:
            lines.append(f"# {section_description}")

        # 添加section头部
        lines.append(f"[{section_name}]")

        # 添加该section下的配置项
        for name, config_item in items.items():
            description = config_item.get('description', '')
            value_type = config_item.get('type', '')
            default_value = config_item.get('value', '')

            # 获取现有值（嵌套结构）
            value_to_use = default_value
            if existing_values:
                # 尝试从嵌套结构中获取值
                if section_name in existing_values and name in existing_values[section_name]:
                    value_to_use = existing_values[section_name][name]
                # 也尝试从扁平路径获取（兼容旧格式）
                elif f"{section_name}.{name}" in existing_values:
                    value_to_use = existing_values[f"{section_name}.{name}"]

            # 格式化值
            toml_value = format_value_for_toml(value_to_use)

            # 添加配置项，注释放在同一行后方
            required_text = " [必须项]" if not is_optional_type(value_type) else " [可选项]"
            lines.append(f"{name} = {toml_value}  # {description}{required_text}")

        # section之间空行分隔
        lines.append("")

    return "\n".join(lines).rstrip("\n")


def format_value_for_toml(value) -> str:
    """将Python值格式化为TOML字符串"""
    if isinstance(value, str):
        if value == '':
            return '""'  # 空字符串
        else:
            # 尝试转换为适当格式
            try:
                # 如果是布尔字符串
                if value.lower() in ('true', 'false'):
                    return value.lower()
                # 如果是数字字符串
                elif value.isdigit():
                    return value
                else:
                    return f'"{value}"'
            except:
                return f'"{value}"'
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif value is None:
        return '""'
    else:
        return f'"{value}"'


def check_file(file_path: Path) -> bool:
    """检查文件是否存在且为普通文件"""
    return file_path.exists() and file_path.is_file()

def generic_config_loader(
    config_class,
    config_path: Path,
    config_type: str = "env",
    logger_prefix: str = "配置"
) -> Dict[str, Any]:
    """
    通用配置加载器

    Args:
        config_class: 配置类（如 env_config, BotConfig）
        config_path: 配置文件路径
        config_type: 配置文件类型，'env' 或 'toml'
        logger_prefix: 日志前缀

    Returns:
        解析后的配置字典
    """
    config_name = config_path.name

    if not check_file(config_path):
        logger.info(f"未找到 {config_name} 文件，尝试创建模板")

        # 根据类型生成模板内容
        if config_type == "env":
            template_content = generate_env_template()
        elif config_type == "toml":
            template_content = generate_toml_template(config_class)
        else:
            logger.error(f"不支持的配置文件类型：{config_type}")
            sys.exit(1)

        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        logger.info(f"已创建{config_name}文件：{config_path}")
        logger.info(f"请填写{config_name}文件并重新启动")
        sys.exit(0)
    
    # 如果配置文件存在，解析并检查
    logger.info(f"发现 {config_name} 文件，开始验证配置项")

    # 解析现有配置
    if config_type == "env":
        existing_config = parse_env_file(config_path)
        logger.success(f"解析.env文件成功")
    elif config_type == "toml":
        existing_config = parse_toml_file(config_path)
        logger.success(f"config配置项验证通过")
    else:
        logger.error(f"不支持的配置文件类型：{config_type}")
        sys.exit(1)

    # 获取配置项定义
    config_items = get_config_items(config_class)

    # 递归收集配置文件中所有键的路径（扁平化）
    def collect_keys(data, prefix=""):
        keys = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                # 递归处理嵌套字典
                keys.extend(collect_keys(value, full_key))
            else:
                keys.append(full_key)
        return keys

    # 收集所有配置键
    all_config_keys = collect_keys(existing_config)

    # 检查配置文件中是否有未在类中定义的配置项
    for config_key in all_config_keys:
        if config_key not in config_items:
            logger.info(f"{logger_prefix}文件中存在未在类中定义的配置项 '{config_key}'，这可能是一个已弃用或尚不支持的配置项")

    missing_required = []
    missing_optional = []
    empty_optional = []
    needs_update = False
    
    # 检查每个配置项
    for name, config_item in config_items.items():
        type_hint = config_item.get('type', str)
        description = config_item.get('description', '')
        default_value = config_item.get('value', '')
        value_type = config_item.get('type', str)
        
        # 判断是否为可选字段：检查 type 是否为Optional 类型
        is_optional = is_optional_type(value_type)

        # 根据配置类型获取现有值
        if config_type == "env":
            # env文件：扁平访问
            config_value = existing_config.get(name)
        else:
            # toml文件：嵌套访问
            config_value = get_nested_value(existing_config, name)

        # 检查配置项是否存在
        if config_value is None:
            # 配置项完全不存在
            if not is_optional:
                missing_required.append(name)
            else:
                missing_optional.append(name)
                needs_update = True
        else:
            # 配置项存在，检查值是否为空
            # 对于 TOML，值可能已经是适当类型，对于 ENV 总是字符串
            if config_type == "env":
                # env 文件中的值总是字符串
                if config_value == '':
                    if not is_optional:
                        # 必须项值为空，使用默认值填充
                        existing_config[name] = default_value
                        needs_update = True
                        logger.warning(f"{logger_prefix}必须项 '{name}' 值为空，已使用默认值：{default_value}")
                    else:
                        empty_optional.append(name)
            else:
                # TOML 文件，值可能已经是适当类型
                # 检查是否为 None（TOML 中缺失或显式设置为 null）
                if config_value is None:
                    if not is_optional:
                        # 使用默认值并设置到嵌套字典中
                        set_nested_value(existing_config, name, default_value)
                        needs_update = True
                        logger.warning(f"{logger_prefix}必须项 '{name}' 值为 None，已使用默认值：{default_value}")
                    else:
                        empty_optional.append(name)

    # 处理必须项缺失 - 自动添加并记录 warning
    if missing_required:
        for name in missing_required:
            config_item = config_items[name]
            description = config_item.get('description', '')
            default_value = config_item.get('value', '')
            logger.error(f"缺少{logger_prefix}必须项：{name} (描述：{description})，已使用默认值：{default_value}")
            if config_type == "env":
                existing_config[name] = default_value
            else:
                set_nested_value(existing_config, name, default_value)
        needs_update = True
    
    # 如果需要更新文件（有缺失或空值的配置项），重新写入完整内容
    if needs_update:
        # 根据类型生成完整内容
        if config_type == "env":
            # 生成完整的.env 内容
            new_lines = []
            for name, config_item in config_items.items():
                description = config_item.get('description', '')
                value_type = config_item.get('type', '')
                default_value = config_item.get('value', '')
                
                # 判断是否为可选字段
                is_optional = is_optional_type(value_type)

                # 使用现有值或默认值
                value = existing_config.get(name, default_value)

                required_text = ""
                if not is_optional:
                    required_text = ' [必须项]'
                else:
                    required_text = ' [可选项]'
                new_lines.append(f"# {description}" + required_text)
                new_lines.append(f"{name}={value}")
                new_lines.append("")

            content = "\n".join(new_lines)
        elif config_type == "toml":
            # 重新生成完整的TOML内容，保留现有值
            content = generate_toml_template(config_class, existing_config)

        # 写入完整的配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"已更新{config_name}文件，补充了缺失的配置项，请重新填写后重启")
        sys.exit(1)
    
    # 处理可选项值为空 - 记录 info
    if empty_optional:
        for name in empty_optional:
            logger.info(f"{logger_prefix}可选项 '{name}' 值为空，请根据需要填写")

    # 返回加载后的配置内容
    return existing_config


def env_loader():
    """加载.env 文件，如果不存在则根据 env_config 创建模板；如果存在则验证完整性并补充缺失项"""
    return generic_config_loader(
        config_class=env_config,
        config_path=env_path,
        config_type="env",
        logger_prefix="环境变量"
    )


def bot_config_loader() -> Dict[str, Any]:
    """加载config.toml文件，如果不存在则根据BotConfig创建模板；如果存在则验证完整性并补充缺失项"""
    return generic_config_loader(
        config_class=BotConfig,
        config_path=config_path,
        config_type="toml",
        logger_prefix="机器人配置"
    )


# 加载 env 环境变量
env = env_loader()
logger.debug(f"加载环境变量文件：{env}")

# 加载机器人配置
config = bot_config_loader()
logger.debug(f"加载机器人配置文件：{config}")

