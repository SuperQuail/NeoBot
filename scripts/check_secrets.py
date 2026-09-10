#!/usr/bin/env python3
"""扫描仓库中的疑似密钥，防止敏感信息被提交。

用法：
    python scripts/check_secrets.py            # 扫描受 Git 跟踪的当前文件
    python scripts/check_secrets.py --staged   # 只扫描暂存区（供 pre-commit 使用）
    python scripts/check_secrets.py --history  # 扫描全部提交历史（较慢）

退出码 0 表示未发现疑似密钥；1 表示发现（已打印 file:line 与命中片段，密钥本身打码）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: 高置信度的密钥形态（宁可少报，也不要因误报而让人习惯性忽略）
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI/兼容平台 Key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("Slack Token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("私钥文件", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

#: 明确的占位符/示例/测试夹具，不算泄漏
ALLOWLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"^sk-x+$"),
    re.compile(r"^sk-\*+$"),
    re.compile(r"\*{3,}(REMOVED|REDACTED)\*{0,}$"),
    re.compile(r"^sk-(abc|zyxw|qwerty|traceback|selfheal|filetrace)[A-Za-z0-9]*$"),
    re.compile(r"^sk-(your|test|demo|example|placeholder)[A-Za-z0-9_-]*$", re.IGNORECASE),
)

TEXT_SUFFIXES = {
    ".py", ".pyi", ".toml", ".md", ".txt", ".json", ".json5", ".yaml", ".yml", ".ini",
    ".cfg", ".env", ".example", ".sh", ".bash", ".ps1", ".psm1", ".bat", ".cmd", ".js",
    ".jsx", ".ts", ".tsx", ".css", ".html", ".htm", ".sql", ".xml", ".csv", ".rst",
    ".gitignore", ".gitattributes", ".properties", ".lock", ".cfg",
}
MAX_BYTES = 2 * 1024 * 1024


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _mask(value: str) -> str:
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}{'*' * 6}{text[-2:]}"


def _load_ignored() -> frozenset[str]:
    """读取仓库根目录 .secretsignore（精确匹配的允许值）。"""
    root = _git("rev-parse", "--show-toplevel").strip()
    path = Path(root or ".") / ".secretsignore"
    if not path.is_file():
        return frozenset()
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            values.add(text)
    return frozenset(values)


_IGNORED: frozenset[str] = _load_ignored()


def _allowed(value: str) -> bool:
    if value in _IGNORED:
        return True
    return any(pattern.search(value) for pattern in ALLOWLIST)


def _scan_text(path: str, text: str) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                if _allowed(value):
                    continue
                findings.append((path, lineno, label, _mask(value)))
    return findings


def _iter_worktree_files() -> list[str]:
    raw = _git("ls-files", "-z")
    return [item for item in raw.split("\0") if item]


def _iter_staged_files() -> list[str]:
    raw = _git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z")
    return [item for item in raw.split("\0") if item]


def scan_files(paths: list[str]) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    for relative in paths:
        path = Path(relative)
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            if path.suffix and path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(_scan_text(relative, text))
    return findings


def scan_history(*, limit: int = 4000) -> list[tuple[str, int, str, str]]:
    """扫描历史提交内容（同一文件多次命中只报告一次）。"""
    commits = [item for item in _git("rev-list", "--all").splitlines() if item][:limit]
    findings: list[tuple[str, int, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, pattern in PATTERNS:
        if not commits:
            break
        output = _git("grep", "-n", "-I", "-E", "-e", pattern.pattern, *commits)
        for line in output.splitlines():
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            _commit, path, lineno, content = parts
            for match in pattern.finditer(content):
                value = match.group(0)
                if _allowed(value):
                    continue
                key = (path, value)
                if key in seen:
                    continue
                seen.add(key)
                findings.append((path, int(lineno or 0), label, _mask(value)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描仓库中的疑似密钥")
    parser.add_argument("--staged", action="store_true", help="只扫描暂存区文件")
    parser.add_argument("--history", action="store_true", help="扫描全部提交历史")
    parser.add_argument("--quiet", action="store_true", help="只输出结论")
    args = parser.parse_args()

    if args.history:
        findings = scan_history()
        scope = "提交历史"
    else:
        paths = _iter_staged_files() if args.staged else _iter_worktree_files()
        findings = scan_files(paths)
        scope = "暂存区" if args.staged else "工作区"

    if not findings:
        if not args.quiet:
            print(f"[check-secrets] {scope}未发现疑似密钥")
        return 0

    print(f"[check-secrets] 在{scope}发现 {len(findings)} 处疑似密钥：", file=sys.stderr)
    for path, lineno, label, masked in findings:
        print(f"  {path}:{lineno}  {label}  {masked}", file=sys.stderr)
    print(
        "请改用环境变量或 .env（.env 不会被提交）；若已提交，需要改写历史并轮换密钥。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
