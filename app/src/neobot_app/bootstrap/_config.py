"""配置加载"""

from __future__ import annotations

from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.plugin_config_migration import migrate_legacy_plugin_config
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE
from neobot_app.utils.logger import get_module_logger


def _load_config() -> BotConfigSchema:
    load_env()
    # 历史 [dashboard] 分区 -> 插件数据目录（配置与启停状态都不再写在本体配置里）
    migrate_legacy_plugin_config(logger=get_module_logger("config_migration"))
    return Config.load(CONFIG_FILE, BotConfigSchema)


def build_config() -> ConfigProxy:
    return ConfigProxy(_load_config())
