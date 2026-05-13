import asyncio
import signal
import sys

from neobot_app.bootstrap import create_application
from neobot_app.runtime.application import ConnectionTimeoutError


async def run() -> None:
    application = create_application()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            if sig == signal.SIGINT:
                signal.signal(
                    signal.SIGINT,
                    lambda _signum, _frame: loop.call_soon_threadsafe(request_stop),
                )

    await application.run_forever()


def main() -> None:
    try:
        asyncio.run(run())
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
