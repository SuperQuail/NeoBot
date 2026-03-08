from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BotConfig:
    """机器人主配置"""
    
    @dataclass
    class Bot:
        """机器人基础配置"""
        account: int = field(
            metadata={
                'description': '机器人QQ号'
            }
        )
    
    @dataclass
    class Plugins:
        """插件配置"""
        enabled: bool = field(
            default=True,
            metadata={
                'description': '是否启用插件'
            }
        )
        dir: str = field(
            default='./plugins',
            metadata={
                'description': '插件目录'
            }
        )
    
    @dataclass
    class Message:
        """消息处理配置"""
        max_length: Optional[int] = field(
            default=1000,
            metadata={
                'description': '消息最大长度'
            }
        )
        enable_group: Optional[bool] = field(
            default=True,
            metadata={
                'description': '是否处理群消息'
            }
        )
        enable_private: Optional[bool] = field(
            default=True,
            metadata={
                'description': '是否处理私聊消息'
            }
        )
    
    # 实例化各个配置模块
    bot: Bot = field(default_factory=Bot)
    plugins: Plugins = field(default_factory=Plugins)
    message: Message = field(default_factory=Message)
