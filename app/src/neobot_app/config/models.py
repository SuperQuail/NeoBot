"""配置模型 — 统一导出"""

from neobot_app.config.schemas.bot import (
    Bot,
    BotConfig,
    Chat,
    KeyWordRule,
    Message,
    Plugins,
)
from neobot_app.config.schemas.env import EnvConfig

__all__ = [
    "Bot",
    "BotConfig",
    "Chat",
    "EnvConfig",
    "KeyWordRule",
    "Message",
    "Plugins",
]
