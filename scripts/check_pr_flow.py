#!/usr/bin/env python3
"""PR 分支流向：main 是默认分支；release 由 QuailEgg 生成和维护。

分支模型（2026-11-07 起）：
- 日常功能/修复 PR → main（仓库默认分支）；
- release 每次发布由 QuailEgg 从 main 重建并强制推送，发布 PR 为 release → main；
- dev 保留为普通分支，不再默认、不再参与发布。

GitHub 分支保护不能限制「源分支」，所以用本脚本在 PR 上做强制检查。
"""

from __future__ import annotations

import argparse
import os
import sys

MAIN = "main"
RELEASE = "release"


def evaluate(base: str, head: str) -> tuple[bool, str]:
    """纯判定：返回 (是否允许, 说明)。"""
    base = str(base or "").strip()
    head = str(head or "").strip()
    if not base or not head:
        return False, "无法读取 PR 的 base/head 分支名。"
    if base == RELEASE:
        return False, (
            "release 由 QuailEgg 生成和维护，不接受人工 PR；"
            "发布走 release → main 的 QuailEgg 发布 PR。"
        )
    if base == MAIN and head == MAIN:
        return False, "不能从 main 向 main 提 PR。"
    return True, f"分支流向允许：{head} → {base}。"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("GITHUB_BASE_REF", ""))
    parser.add_argument("--head", default=os.environ.get("GITHUB_HEAD_REF", ""))
    args = parser.parse_args(argv)

    ok, message = evaluate(args.base, args.head)
    if ok:
        print(message)
        return 0
    print(f"::error::{message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
