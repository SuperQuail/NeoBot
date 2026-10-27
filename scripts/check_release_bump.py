#!/usr/bin/env python3
"""release PR 版本号检查：main → release 必须提升版本号且 8 个项目版本一致。

新的发布流程（2026-10-26 起）：
- dev → main：普通发布候选；
- main → release：该 PR 内把 8 个 pyproject.toml 的版本统一提升，并更新 uv.lock；
- 合并到 release 后由 publish workflow 发布。

本脚本只读检查，不改任何文件。uv.lock 一致性由同 job 的 uv lock --check 保证。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version

PROJECT_FILES = (
    "pyproject.toml",
    "app/pyproject.toml",
    *(
        f"packages/{name}/pyproject.toml"
        for name in (
            "adapter",
            "chat",
            "contracts",
            "memory",
            "modloader",
            "storage",
        )
    ),
)


def read_version(text: str, source: str) -> str:
    data = tomllib.loads(text)
    try:
        return str(data["project"]["version"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{source} 缺少 [project].version") from exc


def compare_versions(base_version: str, head_version: str) -> tuple[bool, str]:
    """纯判定：head 版本必须严格大于 base。"""
    try:
        base = Version(base_version)
        head = Version(head_version)
    except InvalidVersion as exc:
        return False, f"版本号不是合法版本：{exc}"
    if head <= base:
        return False, (
            f"release PR 必须提升版本号：当前 HEAD 为 {head_version}，"
            f"未高于 release 基线 {base_version}。"
        )
    return True, f"版本号已提升：{base_version} → {head_version}。"


def _git_show(base: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{base}:{path}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR 基线（main）的提交 SHA")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="仓库根目录",
    )
    args = parser.parse_args(argv)

    try:
        base_version = read_version(
            _git_show(args.base, "pyproject.toml"), f"{args.base}:pyproject.toml"
        )
        versions = {
            path: read_version(
                (args.repo_root / path).read_text(encoding="utf-8"), path
            )
            for path in PROJECT_FILES
        }
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"::error::读取版本失败：{exc}")
        return 1

    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        print("::error::8 个项目版本不一致：" + ", ".join(distinct))
        return 1

    ok, message = compare_versions(base_version, distinct[0])
    if not ok:
        print(f"::error::{message}")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
