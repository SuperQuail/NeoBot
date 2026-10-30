"""插件 CI 的历史包升级验收入口，只操作新建的隔离宿主。"""

import argparse
import asyncio
import json
from pathlib import Path

from neobot_modloader.sdk.tooling.upgrade_check import check_upgrade


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用合成历史配置和 SQLite 样例验收最终包升级")
    parser.add_argument("previous", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    report = asyncio.run(check_upgrade(args.previous, args.candidate, args.fixture, args.output, timeout=args.timeout))
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
