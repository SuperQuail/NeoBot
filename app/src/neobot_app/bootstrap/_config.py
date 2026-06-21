"""配置加载"""

from __future__ import annotations

from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE


def _load_config() -> BotConfigSchema:
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)


def build_config() -> ConfigProxy:
    return ConfigProxy(_load_config())
