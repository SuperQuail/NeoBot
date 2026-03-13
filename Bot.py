from app.src.neobot_app.config.instance import bot_config
from app.src.neobot_app.utils.logger import get_module_logger
from packages.adapter.src.neobot_adapter.receiver import core

logger = get_module_logger("core")

if __name__ == "__main__":
    logger.info("NeoBot启动中")
    core.initialize_core()
    