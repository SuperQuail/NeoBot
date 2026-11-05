#!/usr/bin/env python3
"""在基础仓库刷新当前 PR head 的门禁，不改变评审判定规则。

fork 的 review 事件无写权限，只读工作流完成后由 workflow_run 接力。
所有 run / PR / head 均重新向 GitHub 读取；relay 标题仅作为数字 PR 标识，
不下载 artifacts、不检出 fork，也不执行事件里的文本或命令。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

RELAY_PATH = ".github/workflows/pr-review-events.yml"
GATE_PATH = ".github/workflows/pr-gates.yml"
RELAY_EVENTS = {"pull_request_review", "pull_request_review_comment"}
Api = Callable[[str, str], Any]


def github_api(method: str, path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", "--method", method, path],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def resolve_pr_number(event_name: str, event: dict, repo: str, api: Api) -> int | None:
    if (event.get("repository") or {}).get("full_name") != repo:
        raise ValueError("事件仓库与当前基础仓库不一致")
    if event_name == "issue_comment":
        issue = event.get("issue") or {}
        number = issue.get("number") if isinstance(issue.get("pull_request"), dict) else None
        return number if type(number) is int and number > 0 else None
    if event_name != "workflow_run":
        raise ValueError("不支持的门禁刷新事件")
    run_id = (event.get("workflow_run") or {}).get("id")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("无效的评审事件 run id")
    # 不信任回调里携带的标题和状态，使用同仓库 API 中的实际 run。
    run = api("GET", f"repos/{repo}/actions/runs/{run_id}")
    if (
        (run.get("repository") or {}).get("full_name") != repo
        or str(run.get("path") or "").split("@", 1)[0] != RELAY_PATH
        or run.get("event") not in RELAY_EVENTS
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        return None
    match = re.fullmatch(r"PR #([1-9][0-9]*)", str(run.get("display_title") or ""))
    return int(match[1]) if match else None


def find_gate_run(repo: str, sha: str, api: Api) -> dict | None:
    # head_sha 由当前 PR API 提供，而不是旧评审事件的 merge SHA。
    for page in range(1, 11):
        query = urlencode({"event": "pull_request", "head_sha": sha, "per_page": 100, "page": page})
        payload = api("GET", f"repos/{repo}/actions/workflows/pr-gates.yml/runs?{query}")
        runs = payload.get("workflow_runs") or []
        matches = [
            run
            for run in runs
            if run.get("head_sha") == sha
            and run.get("event") == "pull_request"
            and str(run.get("path") or "").split("@", 1)[0] == GATE_PATH
            and type(run.get("id")) is int
        ]
        if matches:
            return max(matches, key=lambda run: run["id"])
        if len(runs) < 100:
            return None
    raise RuntimeError("无法在分页上限内定位当前 PR 门禁")


def refresh(
    event_name: str,
    event: dict,
    repo: str,
    api: Api = github_api,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is None:
        raise ValueError("无效的基础仓库名称")
    number = resolve_pr_number(event_name, event, repo, api)
    if number is None:
        print("不是可刷新的 PR 评论/评审事件，跳过。")
        return False
    pr_path = f"repos/{repo}/pulls/{number}"
    pull = api("GET", pr_path)
    if pull.get("state") != "open":
        print(f"PR #{number} 已关闭，跳过。")
        return False
    sha = str((pull.get("head") or {}).get("sha") or "")
    if re.fullmatch(r"[0-9a-f]{40,64}", sha) is None:
        raise ValueError("当前 PR head SHA 无效")
    run = find_gate_run(repo, sha, api)
    if run is None:
        print(f"PR #{number} 当前 head 尚无门禁 run，等待 pull_request 事件创建。")
        return False
    run_path = f"repos/{repo}/actions/runs/{run['id']}"
    # 与原 gh run watch 一样等原 run 结束；任务由工作流的执行时限约束，
    # 不能因为某次排队超过几分钟而丢掉唯一一次评审刷新事件。
    while True:
        current = api("GET", run_path)
        if current.get("status") == "completed":
            break
        sleep(5)
    # 等待期间可能推送或关闭 PR。不能拿旧 SHA 的检查冒充当前检查。
    latest = api("GET", pr_path)
    if latest.get("state") != "open" or (latest.get("head") or {}).get("sha") != sha:
        print(f"PR #{number} 在等待期间已变更，交由新 head 的门禁评估。")
        return False
    api("POST", run_path + "/rerun")
    print(f"已重跑 PR #{number} 的门禁 run {run['id']}（head {sha}）")
    return True


def main() -> int:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        refresh(os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_REPOSITORY"])
    except Exception as exc:
        print(f"::error::刷新 PR 门禁失败：{type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
