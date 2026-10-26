#!/usr/bin/env python3
"""修复类 PR 必须关联 issue：标题以 fix 开头时，PR 必须有关闭关键字关联的 issue。

规则来源（2026-10-26 用户要求）：发现 bug / CI 因 bug 变红，必须先发 issue，
修复 PR 在描述里用 Closes #NN 关联；本门禁只校验「fix PR 有没有关联 issue」，
issue 是否先创建、内容是否对由流程与评审保证。

用法::

    GITHUB_TOKEN=... python scripts/check_pr_issue_link.py --pr 131

退出码：0 = 通过（非 fix 或已关联）；1 = fix PR 没有关联 issue。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
GRAPHQL_URL = f"{API_ROOT}/graphql"
FIX_TITLE_RE = re.compile(r"^fix(?:\([^)]*\))?!?:\s")


def is_fix_title(title: str) -> bool:
    return bool(FIX_TITLE_RE.match(str(title or "").strip()))


def resolve_pr_number(event: dict) -> int | None:
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("number"):
        return int(pull_request["number"])
    issue = event.get("issue")
    if isinstance(issue, dict) and issue.get("pull_request") is not None:
        return int(issue.get("number") or 0) or None
    return None


def evaluate(title: str, linked_count: int) -> tuple[bool, str]:
    if not is_fix_title(title):
        return True, "非 fix 类 PR，不要求关联 issue。"
    if linked_count <= 0:
        return (
            False,
            "fix PR 必须在描述里用 Closes #NN 关联对应的 bug issue；"
            "如果 issue 还没创建，请先创建 issue 再改 PR 描述。",
        )
    return True, f"fix PR 已关联 {linked_count} 个 issue。"


def _graphql(token: str, query: str, variables: dict) -> dict:
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "neobot-pr-issue-gate",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      title
      closingIssuesReferences(first: 10) { totalCount }
    }
  }
}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="PR 编号；默认从 GitHub 事件读取")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or "/" not in repo:
        print("::error::缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY，无法检查 issue 关联。")
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
            print("::error::当前事件不是 PR，无法检查 issue 关联。")
            return 1

    owner, name = repo.split("/", 1)
    try:
        payload = _graphql(token, _QUERY, {"owner": owner, "name": name, "number": pr})
        data = payload.get("data") or {}
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        title = str(pull.get("title") or "")
        linked = int(((pull.get("closingIssuesReferences") or {}).get("totalCount")) or 0)
    except urllib.error.HTTPError as exc:
        print(f"::error::读取 PR 信息失败：HTTP {exc.code} {exc.reason}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CI 门禁要给出可读失败原因
        print(f"::error::读取 PR 信息失败：{type(exc).__name__}: {exc}")
        return 1

    ok, message = evaluate(title, linked)
    if ok:
        print(message)
        return 0
    print(f"::error::{message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
