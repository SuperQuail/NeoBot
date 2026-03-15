"""机器人配置实例"""

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.core import CONFIG_FILE
from neobot_app.database.sqlite import get_db
from neobot_app.message.queue import MessageQueue

# 加载环境变量
load_env()

# 加载机器人配置
bot_config = Config.load(CONFIG_FILE, BotConfig)

# 数据库实例（延迟初始化）
db_instance = get_db()

# 消息队列实例（延迟初始化）
group_message_queue: MessageQueue = None
friend_message_queue: MessageQueue = None

def init_message_queues() -> None:
    """初始化消息队列"""
    global group_message_queue, friend_message_queue

    if group_message_queue is None:
        max_group_obs = bot_config.chat.max_group_chat_observations
        group_message_queue = MessageQueue(max_size=max_group_obs)

    if friend_message_queue is None:
        max_friend_obs = bot_config.chat.max_friend_chat_observations
        friend_message_queue = MessageQueue(max_size=max_friend_obs)
