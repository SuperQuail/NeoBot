"""PR 门禁脚本：体积 / 评审 / issue 关联。

CI 用同一个脚本阻断（.github/workflows/pr-gates.yml）；这里锁住判定规则，
包含阈值边界、事件解析与时间比较。
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _load(name: str):
    spec = importlib.util.spec_from_file_location("neobot_" + name, ROOT / "scripts" / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SIZE = _load("check_pr_size")
REVIEW = _load("check_pr_review")
ISSUE = _load("check_pr_issue_link")
FLOW = _load("check_pr_flow")
BUMP = _load("check_release_bump")


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


# ── 体积 ──


def test_size_thresholds() -> None:
    assert SIZE.evaluate({"a.py": 499}) == ([], [])
    warnings = SIZE.evaluate({"a.py": 500})[1]
    assert warnings and "500" in warnings[0]
    assert SIZE.evaluate({"a.py": 799})[0] == []
    errors, warnings = SIZE.evaluate({"a.py": 800})
    assert errors and errors[0].startswith("a.py")
    assert warnings == []


def test_size_parse_filters_non_code_and_binary() -> None:
    numstat = "\n".join([
        "600\t0\tapp/src/neobot_app/a.py",
        "900\t0\tdocs/guide.md",
        "900\t0\tuv.lock",
        "900\t0\tapp/src/neobot_app/builtin_plugins/dashboard/web/assets/index.js",
        "-\t-\tassets/logo.png",
    ])
    added = SIZE.parse_numstat(numstat)
    assert added == {"app/src/neobot_app/a.py": 600}


def test_size_code_suffixes() -> None:
    assert SIZE.is_code_path("x.tsx")
    assert SIZE.is_code_path("x.py")
    assert not SIZE.is_code_path("x.md")
    assert not SIZE.is_code_path("web/assets/x.js")


def test_size_rename_uses_new_path() -> None:
    assert SIZE._target_path("old.py => new.py") == "new.py"
    assert SIZE._target_path("dir/{old.py => new.py}") == "dir/new.py"
    assert SIZE._target_path("dir/{old => new}/x.py") == "dir/new/x.py"
    assert SIZE._target_path("{weird} => dest.py") == "dest.py"


# ── 评审 ──


def test_review_resolve_event() -> None:
    assert REVIEW.resolve_pr_number({"pull_request": {"number": 7}}) == 7
    assert REVIEW.resolve_pr_number({"issue": {"number": 8, "pull_request": {}}}) == 8
    assert REVIEW.resolve_pr_number({"issue": {"number": 9}}) is None


def test_review_requires_comment_newer_than_commit() -> None:
    commit = _ts("2026-10-26T04:00:00Z")
    ok, message = REVIEW.evaluate([], commit)
    assert ok is False and "还没有" in message
    ok, _ = REVIEW.evaluate([_ts("2026-10-26T03:59:59Z")], commit)
    assert ok is False
    ok, message = REVIEW.evaluate([_ts("2026-10-26T04:00:01Z")], commit)
    assert ok is True and "晚于" in message


def test_review_latest_comment_wins() -> None:
    commit = _ts("2026-10-26T04:00:00Z")
    times = [_ts("2026-10-26T04:10:00Z"), _ts("2026-10-26T03:00:00Z")]
    assert REVIEW.evaluate(times, commit)[0] is True


# ── issue 关联 ──


def test_issue_fix_title_detection() -> None:
    assert ISSUE.is_fix_title("fix(reply): 修复输出")
    assert ISSUE.is_fix_title("fix!: 破坏性修复")
    assert not ISSUE.is_fix_title("feat(ci): 接入门禁")
    assert not ISSUE.is_fix_title("chore: 发版")


def test_issue_link_requires_issue_for_fix_pr() -> None:
    assert ISSUE.evaluate("feat(ci): 接入门禁", 0)[0] is True
    ok, message = ISSUE.evaluate("fix(reply): 修复输出", 0)
    assert ok is False and "Closes" in message
    assert ISSUE.evaluate("fix(reply): 修复输出", 1)[0] is True


def test_issue_script_reads_event_pr_number() -> None:
    assert ISSUE.resolve_pr_number({"pull_request": {"number": 3}}) == 3
    assert ISSUE.resolve_pr_number({"issue": {"number": 4, "pull_request": {}}}) == 4

# ── 分支流向 / 发布版本号 ──


def test_flow_allows_expected_paths() -> None:
    assert FLOW.evaluate("dev", "feat/x")[0] is True
    assert FLOW.evaluate("main", "dev")[0] is True
    assert FLOW.evaluate("release", "main")[0] is True


def test_flow_rejects_wrong_source_branches() -> None:
    assert FLOW.evaluate("main", "feat/x")[0] is False
    assert FLOW.evaluate("release", "dev")[0] is False
    assert FLOW.evaluate("dev", "main")[0] is False
    assert FLOW.evaluate("dev", "release")[0] is False
    assert FLOW.evaluate("main", "dev", "fork/repo", "owner/repo")[0] is False
    assert FLOW.evaluate("release", "main", "fork/repo", "owner/repo")[0] is False
    assert FLOW.evaluate("main", "dev", "owner/repo", "owner/repo")[0] is True


def test_release_bump_requires_strictly_newer_version() -> None:
    assert BUMP.compare_versions("2.0.2a9", "2.0.2a10")[0] is True
    assert BUMP.compare_versions("2.0.2a9", "2.0.2a9")[0] is False
    assert BUMP.compare_versions("2.0.2a10", "2.0.2a9")[0] is False
    assert BUMP.compare_versions("2.0.1", "2.0.2")[0] is True
