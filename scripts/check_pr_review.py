#!/usr/bin/env python3
"""PR 评审门禁：PR 下必须有一条评审评论，且最后一次评审晚于最后一次提交。

规则来源（2026-10-26 用户要求）：
- PR 下必须有评论；允许 AI 评论、允许自评；
- 最后一次 review 必须晚于最后一次 commit；
- AI 自评必须由独立子代理完成，且不得带入开发上下文（流程要求，机器只能校验
  「有评论 + 时间晚于提交」，评论内容由人/AI 自行负责）。

评论来源合并三类：Issue 评论、Review 行内评论、Review 正文（非空）。
时区统一按 UTC 比较；严格「晚于」：评论时间 <= 最后提交时间即失败。

事件支持：pull_request / issue_comment / pull_request_review(_comment)。
用法::

    GITHUB_TOKEN=... python scripts/check_pr_review.py
    GITHUB_TOKEN=... python scripts/check_pr_review.py --pr 131

退出码：0 = 通过；1 = 缺评论或评论已过期（需要重新评审并留言）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_ROOT = "https://api.github.com"


def parse_time(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def resolve_pr_number(event: dict) -> int | None:
    """从 GitHub 事件里取 PR 号；issue_comment 只接受 PR 上的留言。"""
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("number"):
        return int(pull_request["number"])
    issue = event.get("issue")
    if isinstance(issue, dict) and issue.get("pull_request") is not None:
        return int(issue.get("number") or 0) or None
    return None


def evaluate(
    comment_times: list[datetime | None], commit_time: datetime | None
) -> tuple[bool, str]:
    """纯判定：评论存在且最后一次严格晚于最后一次提交。"""
    valid = [item for item in comment_times if item is not None]
    if not valid:
        return (
            False,
            "PR 下还没有评审评论。请在本 PR 下留一条 review 评论"
            "（AI 自评必须由独立子代理完成，且不能带开发上下文）。",
        )
    latest = max(valid)
    if commit_time is None:
        return False, "读不到 PR 最后一次提交时间，无法判断评审是否过期。"
    if latest <= commit_time:
        return (
            False,
            f"最后一次 review 是 {latest.isoformat()}，不晚于最后一次 commit "
            f"{commit_time.isoformat()}；推送新提交后必须重新评审并留言。",
        )
    return (
        True,
        f"通过：最后一次 review {latest.isoformat()} 晚于最后一次 commit "
        f"{commit_time.isoformat()}。",
    )


def _request(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "neobot-pr-review-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_all(path: str, token: str) -> list[dict]:
    items: list[dict] = []
    for page in range(1, 11):
        separator = "&" if "?" in path else "?"
        batch = _request(f"{API_ROOT}{path}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            break
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
    return items


def collect_comment_times(repo: str, pr: int, token: str) -> list[datetime | None]:
    times: list[datetime | None] = []
    for item in _get_all(f"/repos/{repo}/issues/{pr}/comments", token):
        times.append(parse_time(item.get("created_at")))
    for item in _get_all(f"/repos/{repo}/pulls/{pr}/comments", token):
        times.append(parse_time(item.get("created_at")))
    for item in _get_all(f"/repos/{repo}/pulls/{pr}/reviews", token):
        if str(item.get("body") or "").strip():
            times.append(parse_time(item.get("submitted_at")))
    return times


def fetch_last_commit_time(repo: str, pr: int, token: str) -> datetime | None:
    pull = _request(f"{API_ROOT}/repos/{repo}/pulls/{pr}", token)
    if not isinstance(pull, dict):
        return None
    head = pull.get("head") or {}
    sha = str(head.get("sha") or "")
    if not sha:
        return None
    commit = _request(f"{API_ROOT}/repos/{repo}/commits/{sha}", token)
    if not isinstance(commit, dict):
        return None
    inner = commit.get("commit") or {}
    return parse_time(
        (inner.get("committer") or {}).get("date")
        or (inner.get("author") or {}).get("date")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="PR 编号；默认从 GitHub 事件读取")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or not repo:
        print("::error::缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY，无法检查 PR 评审。")
        return 1

    pr = args.pr
    if pr is None:
        event_path = os.environ.get("GITHUB_EVENT_PATH") or ""
        try:
            with open(event_path, encoding="utf-8") as handle:
                event = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"::error::读取 GitHub 事件失败：{exc}")
            return 1
        pr = resolve_pr_number(event)
        if pr is None:
            print("::error::当前事件不是 PR，无法检查评审。")
            return 1

    try:
        comment_times = collect_comment_times(repo, pr, token)
        commit_time = fetch_last_commit_time(repo, pr, token)
    except urllib.error.HTTPError as exc:
        print(f"::error::读取 PR 信息失败：HTTP {exc.code} {exc.reason}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CI 门禁要给出可读失败原因
        print(f"::error::读取 PR 信息失败：{type(exc).__name__}: {exc}")
        return 1

    ok, message = evaluate(comment_times, commit_time)
    if ok:
        print(message)
        return 0
    print(f"::error::{message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
