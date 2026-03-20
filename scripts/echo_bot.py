"""Echo 示例 — 收到 /echo xxx 就回复 xxx。

用法: uv run python scripts/echo_bot.py
"""

import asyncio
import signal

import loguru

from neobot_adapter import OneBotAdapter
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_app.message.queue import MessageQueue
from neobot_app.observability.logging import LoguruLoggerAdapter
from neobot_app.runtime.event_pipeline import EventPipeline


async def main():
    logger = LoguruLoggerAdapter(loguru.logger)
    adapter = OneBotAdapter(logger=logger)

    # 启动事件管线（打印收到的消息）
    pipeline = EventPipeline(
        adapter,
        group_message_queue=MessageQueue(),
        friend_message_queue=MessageQueue(),
        logger=logger,
    )
    pipeline.start()

    @adapter.on.message(group=True)
    async def on_group_msg(event: GroupMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            text = event.raw_message[6:]
            await adapter.send_group_msg(group_id=event.group_id, message=text)

    @adapter.on.message(private=True)
    async def on_private_msg(event: PrivateMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            text = event.raw_message[6:]
            await adapter.send_private_msg(user_id=event.user_id, message=text)

    await adapter.start()
    print("Echo Bot 已启动，等待 OneBot 框架连接...")

    connected = await asyncio.to_thread(adapter.wait_for_connection, 60)
    if not connected:
        print("等待连接超时")
        await adapter.stop()
        return

    print("OneBot 框架已连接，发送 /echo 你好 试试")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    print("\n正在停止...")
    pipeline.stop()
    await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
