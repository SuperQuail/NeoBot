from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("格式化器")

class SafeDict(dict):
    """当键缺失时，返回原占位符字符串，例如 '{key}'"""
    def __missing__(self, key):
        logger.debug(f"缺失键:{key}")
        return '{' + key + '}'

def safe_format(template: str, **kwargs) -> str:
    """
    安全格式化字符串，缺失的占位符保持原样。

    :param template: 包含占位符的字符串，如 '群名是{group_name}'
    :param kwargs: 提供的变量值
    :return: 格式化后的字符串
    """
    return template.format_map(SafeDict(**kwargs))