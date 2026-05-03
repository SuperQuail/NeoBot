import asyncio
import signal
import sys

from neobot_app.bootstrap import create_application
from neobot_app.runtime.application import ConnectionTimeoutError


async def main() -> None:
    application = create_application()

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: add_signal_handler 不支持 SIGINT，改用 signal.signal
            if sig == signal.SIGINT:
                signal.signal(
                    signal.SIGINT,
                    lambda _signum, _frame: loop.call_soon_threadsafe(_request_stop),
                )

    await application.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")
    except KeyboardInterrupt:
        sys.exit(0)


