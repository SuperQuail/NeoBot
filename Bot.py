import asyncio
import signal

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_contracts.models import ConversationRef
from neobot_app.bootstrap import create_application
from neobot_app.runtime.application import ConnectionTimeoutError


async def main() -> None:
    application = create_application()
    adapter = application.adapter

    # Echo 测试命令
    @adapter.on.message(group=True)
    async def _echo_group(event: GroupMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            conversation = ConversationRef(kind="group", id=str(event.group_id))
            await adapter.send(conversation, event.raw_message[6:])

    @adapter.on.message(private=True)
    async def _echo_private(event: PrivateMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            conversation = ConversationRef(kind="private", id=str(event.user_id))
            await adapter.send(conversation, event.raw_message[6:])

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    await application.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")


