import asyncio
import signal

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_app.bootstrap import create_application
from neobot_app.runtime.application import ConnectionTimeoutError


async def main() -> None:
    application = create_application()
    adapter = application.adapter

    # Echo 测试命令
    @adapter.on.message(group=True)
    async def _echo_group(event: GroupMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            await adapter.send_group_msg(group_id=event.group_id, message=event.raw_message[6:])

    @adapter.on.message(private=True)
    async def _echo_private(event: PrivateMessage):
        if event.raw_message and event.raw_message.startswith("/echo "):
            await adapter.send_private_msg(user_id=event.user_id, message=event.raw_message[6:])

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
