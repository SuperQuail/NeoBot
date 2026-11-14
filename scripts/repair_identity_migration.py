"""a10→a11 个人档案修复 CLI（逻辑在 neobot_app.database.identity_repair）。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from neobot_app.database.identity_repair import repair


def main() -> int:
    parser = argparse.ArgumentParser(description="修复 a10 错误身份迁移留下的个人档案")
    parser.add_argument("--data-dir", default="app/data")
    parser.add_argument("--apply", action="store_true", help="真正写库；默认 dry-run")
    parser.add_argument("--dry-run", action="store_true", help="只预览（默认）")
    parser.add_argument("--include-history", action="store_true", help="额外恢复消息/记忆等 ID")
    parser.add_argument("--include-plugins", action="store_true", help="额外恢复 agent/插件库")
    args = parser.parse_args()
    result = repair(
        Path(args.data_dir),
        bool(args.apply and not args.dry_run),
        include_history=args.include_history,
        include_plugins=args.include_plugins,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
