import asyncio
import os

from neobot_app.config.instance import bot_config
from neobot_app.utils.logger import get_module_logger
from neobot_app.database.chatstream import initialize_chat_stream
from neobot_adapter.receiver.core import get_core,initialize_core

logger = get_module_logger("core")

async def main():
    logger.info("NeoBot启动中")
    core = get_core()
    core.start()
    initialize_core(max_queue_size=1000)
    if not core.wait_for_connection(timeout=30):
        print("错误: 连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws")
    logger.info("NeoBot适配器核心启动完成")
    await initialize_chat_stream()
    logger.info("NeoBot聊天流初始化完成")


if __name__ == "__main__":
    asyncio.run(main())