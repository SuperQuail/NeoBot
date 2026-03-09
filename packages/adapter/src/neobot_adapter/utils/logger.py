from typing import TYPE_CHECKING
import loguru

if TYPE_CHECKING:
    from loguru import Logger


def get_module_logger(module_name: str) -> "Logger":
    """
    获取带有自定义模块名称的 logger

    Args:
        module_name: 模块名称，会在 logger 中显示

    Returns:
        绑定了对应模块名称的 logger 实例
    """
    return loguru.logger.bind(module_name=module_name)
