from loguru import logger
from typing import Literal, Optional

#TODO:完全没实现

# 预设颜色配置 (RGB 格式)
PRESET_COLORS = {
    "cyan": (0, 255, 255),      # 青色
    "red": (255, 0, 0),         # 红色
    "purple": (128, 0, 128),    # 紫色
    "yellow": (255, 255, 0),    # 黄色
    "blue": (0, 128, 255),      # 蓝色
}

def get_module_logger(
    module_name: str,
    color: Optional[Literal["cyan", "red", "purple", "yellow", "blue"]] = "cyan",
    custom_rgb: Optional[tuple[int, int, int]] = None,
) -> logger:
    """
    获取带有自定义模块名称和颜色的 logger
    
    Args:
        module_name: 模块名称，会在 logger 中显示
        color: 预设颜色选项，可选值：cyan(青色), red(红色), purple(紫色), yellow(黄色), blue(蓝色)
              默认为 cyan
        custom_rgb: 自定义 RGB 颜色值，格式为 (R, G, B)，优先级高于 color 参数
    
    Returns:
        绑定了对应模块名称的 logger 实例
    
    Example:
        >>> logger = get_module_logger("MyModule")
        >>> logger = get_module_logger("ErrorModule", color="red")
        >>> logger = get_module_logger("CustomModule", custom_rgb=(255, 128, 0))
    """
    # 确定使用的 RGB 颜色
    if custom_rgb is not None:
        rgb_color = custom_rgb
    else:
        rgb_color = PRESET_COLORS.get(color, PRESET_COLORS["cyan"])
    
    # 创建带颜色的模块名称标识
    colored_module_name = f"<fg {rgb_color[0]},{rgb_color[1]},{rgb_color[2]}>[{module_name}]</>"
    logger_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:} | " + f"{colored_module_name}" + ":{function}:{line} - {message}"
    
    # 绑定模块名称并返回 logger
    return logger.bind(format = logger_format)