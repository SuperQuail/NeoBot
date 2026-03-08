from typing import Optional

class BotConfig:
    """机器人主配置"""

    class bot:
        """机器人基础配置"""
        ACCOUNT = {'value': 0, 'type': [int], 'description': '机器人 QQ 账号'}

    class plugins:
        """插件配置"""
        ENABLED = {'value': True, 'type': Optional[bool], 'description': '是否启用插件系统'}
        DIR = {'value': './plugins', 'type': Optional[str], 'description': '插件目录路径'}

    class message:
        """消息处理配置"""
        MAX_LENGTH = {'value': 5000, 'type': Optional[int], 'description': '最大消息长度限制'}
        ENABLE_GROUP = {'value': True, 'type': Optional[bool], 'description': '是否处理群消息'}
        ENABLE_PRIVATE = {'value': True, 'type': Optional[bool], 'description': '是否处理私聊消息'}
