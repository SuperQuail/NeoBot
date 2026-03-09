"""机器人配置实例"""

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.core import CONFIG_FILE

# 加载环境变量
load_env()

# 加载机器人配置
bot_config = Config.load(CONFIG_FILE, BotConfig)
