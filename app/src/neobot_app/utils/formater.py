import re

from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("格式化器")

class SafeDict(dict):
    """当键缺失时，返回原占位符字符串，例如 '{key}'"""
    def __missing__(self, key):
        logger.debug(f"缺失键:{key}")
        return '{' + key + '}'

def safe_format(template: str, **kwargs) -> str:
    """
    安全格式化字符串，缺失的占位符保持原样

    :param template: 包含占位符的字符串，如 '群名是{group_name}'
    :param kwargs: 提供的变量值
    :return: 格式化后的字符串
    """
    try:
        return template.format_map(SafeDict(**kwargs))
    except (ValueError, KeyError, AttributeError, IndexError, TypeError):
        # 模板含畸形花括号(如单个 { 或 }、非法格式说明)时,format_map 会抛异常。
        # 退化为单遍替换已知占位符(正则一次扫描,避免逐 key replace 的值二次替换),
        # 畸形部分原样保留,避免整个会话的回复全部失败。
        logger.warning("提示词模板包含畸形占位符,已降级为仅替换已知占位符")

        def _replacer(match: "re.Match[str]") -> str:
            key = match.group(1)
            return str(kwargs[key]) if key in kwargs else match.group(0)

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", _replacer, template)