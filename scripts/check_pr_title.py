#!/usr/bin/env python3
"""PR 标题体检：仓库 squash 设置为 ``PR_TITLE`` + ``PR_BODY``。

PR 标题会成为 main 上的提交标题、PR 描述会成为提交正文，所以 PR 标题必须符合
commit message 规范——它会永久留在 ``git log`` 与 release notes 里。
提交信息不进 main（除非有人改用 rebase 合并），因此不在这里校验。

用法::

    python scripts/check_pr_title.py --title "fix(reply): 修复输出前缀"
    PR_TITLE="fix(reply): 修复输出前缀" python scripts/check_pr_title.py

退出码：0 = 合规（可能有警告）；1 = 命中阻断项。``--strict`` 让警告也阻断。

在 GitHub Actions 里会额外输出 ``::error::`` / ``::warning::`` 注解，直接标在 PR 页面上。

阻断项只放**机械可判**的规则（格式、长度、`(#NN)`、空话、`——` / ` + ` 清单写法）；
「并列项到底是领域词还是具体改动」需要人判断，只给警告，加 ``--strict`` 才阻断。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

#: 允许的提交类型（约定式提交，见 docs/06-开发指南.md）。
TYPES = ("feat", "fix", "docs", "refactor", "test", "chore", "perf")

#: 标题总显示宽度上限，对应 git 的 72 列约定；中文/全角按 2 列计。
MAX_WIDTH = 72

_TITLE_RE = re.compile(
    r"^(?P<type>" + "|".join(TYPES) + r")"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9._/-]*)\))?"
    r"(?P<breaking>!)?: (?P<desc>.+)$"
)

#: 这些「简述」等于没说，标题要能独立看懂。
_EMPTY_DESCRIPTIONS = frozenset(
    {
        "更新",
        "更新代码",
        "更新文件",
        "修改",
        "修改代码",
        "优化",
        "优化代码",
        "重构",
        "修复",
        "修复问题",
        "修复若干问题",
        "修复bug",
        "修复 bug",
        "发版",
        "提交",
        "临时提交",
        "wip",
        "update",
        "updates",
        "update code",
        "fix",
        "fix bug",
        "fixes",
        "bugfix",
        "bug fix",
        "refactor",
        "improve",
        "misc",
    }
)

#: 「主题 —— 明细」「A + B + C」这类清单写法：明细应该逐条下沉到 body。
_LIST_MARKERS = ("——", " + ", "＋")

#: 并列分隔符：可能是清单，也可能只是领域并列（如「取消、重启与配置」），只警告。
_PARALLEL_MARKERS = ("、", " / ")


def display_width(text: str) -> int:
    """标题的显示宽度：东亚宽字符按 2 列，其余按 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1 for ch in text)


def validate(title: str) -> tuple[list[str], list[str]]:
    """校验标题，返回 ``(阻断项, 警告项)``。空标题算阻断项。"""
    errors: list[str] = []
    warnings: list[str] = []

    raw = title
    if "\n" in raw.strip() or "\r" in raw:
        errors.append("标题不能包含换行")
    text = " ".join(raw.split())
    if not text:
        return ["标题为空"], warnings

    match = _TITLE_RE.match(text)
    if match is None:
        errors.append(
            "标题不符合约定式提交：应为 `<type>(<scope>): <简述>`，"
            f"type 只能取 {'/'.join(TYPES)}，冒号后必须有一个空格和简述"
        )
    else:
        desc = match.group("desc").strip()
        if desc.endswith((".", "。")):
            errors.append("简述结尾不要加句号")
        if desc.lower() in _EMPTY_DESCRIPTIONS:
            errors.append(f"简述「{desc}」没有信息量：写清这次改了什么")
        if match.group("breaking"):
            warnings.append("破坏性变更（!）必须在 body 的「行为变化与迁移」里给出迁移步骤")

    if re.search(r"\(#\d+\)$", text):
        errors.append("标题不要自带 `(#NN)`：squash 合并时 GitHub 会自动补")

    width = display_width(text)
    if width > MAX_WIDTH:
        errors.append(f"标题显示宽度 {width} 超过 {MAX_WIDTH}（中文/全角按 2 计）：精简标题，明细下沉到 body")

    for marker in _LIST_MARKERS:
        if marker in text:
            errors.append(f"标题里的「{marker.strip()}」是清单写法：标题只写概括，子改动逐条下沉到 body")

    if sum(text.count(marker) for marker in _PARALLEL_MARKERS) >= 2:
        warnings.append(
            "标题里有多处并列：如果并列的是具体改动（而不是「取消、重启与配置」这类领域词），请下沉到 body 逐条写"
        )

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 PR 标题是否符合 commit message 规范")
    parser.add_argument("--title", default=None, help="PR 标题；省略时读环境变量 PR_TITLE")
    parser.add_argument("--strict", action="store_true", help="警告也视为失败")
    args = parser.parse_args(argv)

    title = args.title if args.title is not None else os.environ.get("PR_TITLE", "")
    errors, warnings = validate(title)

    # Windows 中文控制台的 GBK 编码遇到个别字符会抛 UnicodeEncodeError，
    # 宁可显示成问号也不要让校验脚本崩掉（版本号脚本踩过同一个坑）。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    online = os.environ.get("GITHUB_ACTIONS") == "true"
    print(f"标题：{' '.join(title.split()) or '（空）'}")
    for message in errors:
        print(f"::error::{message}" if online else f"[错误] {message}")
    for message in warnings:
        print(f"::warning::{message}" if online else f"[警告] {message}")

    if errors:
        print("标题校验未通过。这行字会成为 main 上的提交信息，规则见 AGENTS.md 的「Pull Request/Commit Message」。")
        return 1
    if warnings and args.strict:
        print("标题校验未通过（--strict：警告视为失败）。")
        return 1
    print("标题校验通过。" + ("（有警告，未阻断）" if warnings else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
