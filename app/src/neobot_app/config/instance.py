"""机器人配置实例

已弃用：全局单例已移除所有对象装配请通过 bootstrap.py 完成
此模块仅保留向后兼容的配置加载辅助函数，供 chatstream 等尚未完全迁移的模块使用
"""

from __future__ import annotations

from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE


def load_bot_config() -> BotConfigSchema:
    """加载并返回 BotConfig，不缓存为全局变量"""
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)
