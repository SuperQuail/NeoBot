"""启动可交互的本地插件演示，不连接真实 QQ 或直播平台。"""

import argparse
import asyncio
from pathlib import Path
import tempfile

from plugin_demo.host import REPO_ROOT, serve_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="启动真实插件包和面板的隔离演示")
    parser.add_argument("--port", type=int, default=19981)
    parser.add_argument("--sample", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    base = REPO_ROOT / "tmp" / "plugin-demos"
    base.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="session-", dir=base))
    try:
        asyncio.run(serve_demo(data_dir, port=arguments.port, samples=tuple(arguments.sample)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
