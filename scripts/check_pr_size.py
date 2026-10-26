#!/usr/bin/env python3
"""PR 体积体检：单个代码文件新增 500 行警告、800 行阻断。

为什么按「单个文件的新增行」而不是仓库存量：存量里 orchestrator / 测试文件早已
超过千行，按存量判会把所有 PR 一律判红；这里拦的是「这一次又往一个文件里堆了
一大坨」，那才是耦合风险的增量来源。

只统计代码文件（.py/.ts/.tsx/.js/.jsx/.css 等），跳过文档、锁文件与前端构建产物；
生成物（web/assets）不参与。

用法::

    python scripts/check_pr_size.py --base <base-sha> --head <head-sha>

退出码：0 = 通过（可能带警告）；1 = 命中 800 行阻断项。
在 GitHub Actions 里输出 ::warning file=... / ::error file=... 注解。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

WARN_ADDED_LINES = 500
BLOCK_ADDED_LINES = 800

CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".vue",
        ".css",
        ".scss",
        ".html",
    }
)
#: 生成物 / 第三方目录：不是人写的代码，不参与体积判定。
EXCLUDED_PARTS = ("/web/assets/", "/node_modules/", "/dist/", "/.venv/")


def is_code_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    haystack = "/" + normalized.lstrip("/")
    if any(part in haystack for part in EXCLUDED_PARTS):
        return False
    return any(normalized.endswith(suffix) for suffix in CODE_SUFFIXES)


def parse_numstat(numstat: str) -> dict[str, int]:
    """把 git diff --numstat 输出解析成 {路径: 新增行数}（二进制跳过）。"""
    added: dict[str, int] = {}
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        raw_added, _raw_deleted, path = parts
        if raw_added == "-" or not is_code_path(path):
            continue
        added[path] = int(raw_added)
    return added


def evaluate(added: dict[str, int]) -> tuple[list[str], list[str]]:
    """返回 (阻断项, 警告项) 的可读消息列表。"""
    errors: list[str] = []
    warnings: list[str] = []
    for path, lines in sorted(added.items()):
        if lines >= BLOCK_ADDED_LINES:
            errors.append(
                f"{path} 本次新增 {lines} 行，超过 {BLOCK_ADDED_LINES} 行硬上限（过耦合）；"
                "请拆分文件或拆成多个 PR。"
            )
        elif lines >= WARN_ADDED_LINES:
            warnings.append(
                f"{path} 本次新增 {lines} 行，达到 {WARN_ADDED_LINES} 行警戒线（耦合风险）；"
                "建议拆分文件。"
            )
    return errors, warnings


def _git_numstat(base: str, head: str) -> str:
    # --no-renames：重命名按「删除旧文件 + 新增新文件」计，新增行归属清晰。
    result = subprocess.run(
        ["git", "diff", "--numstat", "--no-renames", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR 基线 SHA")
    parser.add_argument("--head", required=True, help="PR 最新提交 SHA")
    args = parser.parse_args(argv)

    try:
        numstat = _git_numstat(args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print(f"::error::读取 PR diff 失败：{exc.stderr or exc}")
        return 1

    added = parse_numstat(numstat)
    errors, warnings = evaluate(added)

    for message in warnings:
        print(f"::warning::{message}")
    for message in errors:
        print(f"::error::{message}")

    if errors:
        print(f"体积门禁失败：{len(errors)} 个文件超过 {BLOCK_ADDED_LINES} 行。")
        return 1
    print(
        f"体积门禁通过：{len(added)} 个代码文件参与检查，"
        f"无文件新增超过 {BLOCK_ADDED_LINES} 行。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
