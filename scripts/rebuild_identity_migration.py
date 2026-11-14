"""a10→a11 全量回滚重建入口（默认放弃 a10 人工映射，恢复迁移前快照）。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from neobot_app.database.identity_repair import auto_rebuild_if_a10_migration


def main() -> int:
    parser = argparse.ArgumentParser(description="a10→a11 全量回滚身份迁移")
    parser.add_argument("--data-dir", default="app/data")
    parser.add_argument("--apply", action="store_true", help="真正恢复；默认 dry-run")
    parser.add_argument("--force", action="store_true", help="已有 marker 也再次回滚（丢弃 a11 数据）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写库（默认）")
    args = parser.parse_args()
    from neobot_app.utils.logger import get_module_logger

    rebuilt = auto_rebuild_if_a10_migration(
        Path(args.data_dir), get_module_logger("rebuild"), apply=bool(args.apply and not args.dry_run), force=args.force
    )
    print(json.dumps({"rebuilt": rebuilt, "apply": args.apply}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
