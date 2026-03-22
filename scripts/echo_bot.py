"""Echo 示例 — 收到 /echo xxx 就回复 xxx。

用法: uv run python scripts/echo_bot.py
"""

import asyncio
import signal
from pathlib import Path

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_app.bootstrap import create_application
from neobot_contracts.models import ConversationRef


async def main():
    application = create_application()
    adapter = application.adapter
    file_server = application.file_server

    @adapter.on.message(group=True)
    async def on_group_msg(event: GroupMessage):
        conversation = ConversationRef(kind="group", id=str(event.group_id))
        if event.raw_message and event.raw_message.startswith("/echo "):
            await adapter.send(conversation, event.raw_message[6:])
        elif event.raw_message and event.raw_message == "/image":
            url = file_server.register_file(Path("docs/neobot.jpg"))
            await adapter.send(conversation, [{"type": "image", "data": {"file": url}}])

    @adapter.on.message(private=True)
    async def on_private_msg(event: PrivateMessage):
        conversation = ConversationRef(kind="private", id=str(event.user_id))
        if event.raw_message and event.raw_message.startswith("/echo "):
            await adapter.send(conversation, event.raw_message[6:])
        elif event.raw_message and event.raw_message == "/image":
            url = file_server.register_file(Path("docs/neobot.jpg"))
            await adapter.send(conversation, [{"type": "image", "data": {"file": url}}])

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    print("命令: /echo <文本> 或 /image")
    await application.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
