#!/usr/bin/env python3
"""PR 分支流向：dev 是默认开发分支；main 只接收 dev；release 只接收 main。

新的分支设计（2026-10-26 起）：
- 日常 PR → dev（仓库默认分支）；
- 发布前 dev → main（main 只允许来自 dev 的 PR）；
- 正式发布 main → release：这条 PR 必须提升版本号，合并后由 release 分支触发 PyPI 发布。

GitHub 分支保护不能限制「源分支」，所以用本脚本在 PR 上做强制检查。
"""

from __future__ import annotations

import argparse
import os
import sys

DEV = "dev"
MAIN = "main"
RELEASE = "release"


def evaluate(
    base: str,
    head: str,
    head_repo: str = "",
    base_repo: str = "",
) -> tuple[bool, str]:
    """纯判定：返回 (是否允许, 说明)。

    head_repo/base_repo 用于拦 fork 里的同名 dev/main 分支：
    往 main/release 提 PR 时，源分支必须来自本仓库。
    """
    base = str(base or "").strip()
    head = str(head or "").strip()
    head_repo = str(head_repo or "").strip()
    base_repo = str(base_repo or "").strip()
    if not base or not head:
        return False, "无法读取 PR 的 base/head 分支名。"
    if (
        base in (MAIN, RELEASE)
        and head_repo
        and base_repo
        and head_repo.casefold() != base_repo.casefold()
    ):
        return False, f"{base} 只接收本仓库的分支，当前源仓库是 {head_repo}。"
    if base == MAIN:
        if head != DEV:
            return False, f"main 只接收来自 {DEV} 的 PR，当前源分支是 {head}。"
        return True, f"分支流向正确：{head} → {base}。"
    if base == RELEASE:
        if head != MAIN:
            return False, (
                f"release 只接收来自 {MAIN} 的 PR，当前源分支是 {head}；"
                "发布走 main → release，并在该 PR 内提升版本号。"
            )
        return True, f"分支流向正确：{head} → {base}（记得提升版本号）。"
    if base == DEV and head in (MAIN, RELEASE):
        return False, f"{DEV} 只接收功能分支，不能从 {head} 反向 PR 到 {DEV}。"
    return True, f"分支流向允许：{head} → {base}。"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("GITHUB_BASE_REF", ""))
    parser.add_argument("--head", default=os.environ.get("GITHUB_HEAD_REF", ""))
    parser.add_argument("--head-repo", default=os.environ.get("PR_HEAD_REPO", ""))
    parser.add_argument("--base-repo", default=os.environ.get("PR_BASE_REPO", ""))
    args = parser.parse_args(argv)

    ok, message = evaluate(args.base, args.head, args.head_repo, args.base_repo)
    if ok:
        print(message)
        return 0
    print(f"::error::{message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
