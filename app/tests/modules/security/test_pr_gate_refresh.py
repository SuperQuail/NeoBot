"""刷新只重跑当前 head 的原门禁，fork 评审上下文不持有写权限。"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("refresh_pr_gates", ROOT / "scripts/refresh_pr_gates.py")
assert spec is not None and spec.loader is not None
REFRESH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REFRESH)
REPO = "SuperQuail/NeoBot"
SHA = "a" * 40


class Api:
    def __init__(self):
        self.calls = []
        self.pull = {"state": "open", "head": {"sha": SHA}}
        self.latest = None
        self.pull_reads = 0
        self.relay = {
            "repository": {"full_name": REPO},
            "path": REFRESH.RELAY_PATH,
            "event": "pull_request_review",
            "status": "completed",
            "conclusion": "success",
            "display_title": "PR #7",
            # fork 评审实际返回空关联，head_sha 也可能是 merge SHA。
            "pull_requests": [],
            "head_sha": "b" * 40,
        }
        self.runs = [dict(id=20, head_sha=SHA, event="pull_request", path=REFRESH.GATE_PATH)]
        self.statuses = ["completed"]
        self.pages = None

    def __call__(self, method, path):
        self.calls.append((method, path))
        if method == "POST":
            assert path == f"repos/{REPO}/actions/runs/20/rerun"
            return None
        if path.endswith("/pulls/7"):
            self.pull_reads += 1
            return copy.deepcopy(self.latest if self.pull_reads > 1 and self.latest is not None else self.pull)
        if path.endswith("/actions/runs/9"):
            return copy.deepcopy(self.relay)
        if "/actions/workflows/pr-gates.yml/runs?" in path:
            assert f"head_sha={SHA}" in path
            page = int(path.rsplit("page=", 1)[1])
            return {"workflow_runs": copy.deepcopy(self.pages[page - 1] if self.pages else self.runs)}
        if path.endswith("/actions/runs/20"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {"status": status}
        raise AssertionError((method, path))

    @property
    def writes(self):
        return [path for method, path in self.calls if method == "POST"]


def event():
    return {"repository": {"full_name": REPO}, "workflow_run": {"id": 9, "display_title": "PR #999"}}


@pytest.mark.parametrize("source", ["pull_request_review", "pull_request_review_comment"])
def test_fork_review_refreshes_current_head_without_pr_association(source):
    api = Api()
    api.relay["event"] = source
    assert REFRESH.refresh("workflow_run", event(), REPO, api)
    assert api.writes == [f"repos/{REPO}/actions/runs/20/rerun"]


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": {"full_name": "attacker/fork"}},
        {"path": ".github/workflows/other.yml"},
        {"event": "push"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"display_title": "PR #7; echo injected"},
        {"display_title": "PR #0"},
    ],
)
def test_unrelated_or_invalid_relay_cannot_rerun(changes):
    api = Api()
    api.relay.update(changes)
    assert REFRESH.refresh("workflow_run", event(), REPO, api) is False
    assert api.writes == []
    assert api.pull_reads == 0


def test_normal_pr_comment_still_refreshes_and_regular_issue_does_not():
    api = Api()
    payload = {"repository": {"full_name": REPO}, "issue": {"number": 7, "pull_request": {}}}
    assert REFRESH.refresh("issue_comment", payload, REPO, api)
    payload["issue"].pop("pull_request")
    unused = Api()
    assert REFRESH.refresh("issue_comment", payload, REPO, unused) is False
    assert unused.calls == []


def test_wrong_repository_event_is_rejected_before_any_api_call():
    api = Api()
    payload = event()
    payload["repository"]["full_name"] = "attacker/fork"
    with pytest.raises(ValueError, match="仓库"):
        REFRESH.refresh("workflow_run", payload, REPO, api)
    assert api.calls == []


def test_only_original_gate_workflow_for_current_head_is_selected():
    api = Api()
    api.runs += [
        dict(id=100, head_sha="b" * 40, event="pull_request", path=REFRESH.GATE_PATH),
        dict(id=101, head_sha=SHA, event="push", path=REFRESH.GATE_PATH),
        dict(id=102, head_sha=SHA, event="pull_request", path=".github/workflows/untrusted.yml"),
    ]
    assert REFRESH.refresh("workflow_run", event(), REPO, api)
    assert api.writes == [f"repos/{REPO}/actions/runs/20/rerun"]


def test_gate_run_pages_are_followed():
    api = Api()
    api.pages = [[dict(id=n, head_sha="b" * 40) for n in range(100)], api.runs]
    assert REFRESH.refresh("workflow_run", event(), REPO, api)
    assert len([path for _, path in api.calls if "workflows/pr-gates.yml/runs?" in path]) == 2


@pytest.mark.parametrize(
    "latest", [{"state": "closed", "head": {"sha": SHA}}, {"state": "open", "head": {"sha": "c" * 40}}]
)
def test_head_change_or_close_while_waiting_cannot_refresh_old_head(latest):
    api = Api()
    api.statuses = ["queued", "in_progress", "completed"]
    api.latest = latest
    sleeps = []
    assert REFRESH.refresh("workflow_run", event(), REPO, api, sleep=sleeps.append) is False
    assert sleeps == [5, 5]
    assert api.writes == []


def test_missing_run_is_not_replaced_by_another_workflow_or_head():
    api = Api()
    api.runs = []
    assert REFRESH.refresh("workflow_run", event(), REPO, api) is False
    assert api.writes == []


def test_slow_gate_keeps_the_review_refresh_event():
    api = Api()
    api.statuses = ["in_progress"] * 61 + ["completed"]
    sleeps = []
    assert REFRESH.refresh("workflow_run", event(), REPO, api, sleep=sleeps.append)
    assert len(sleeps) == 61
    assert api.writes == [f"repos/{REPO}/actions/runs/20/rerun"]


def test_api_failure_while_waiting_does_not_rerun_active_gate():
    api = Api()
    api.statuses = ["in_progress"]
    sleeps = []

    def unavailable(method, path):
        if len(sleeps) == 2:
            raise ConnectionError("API unavailable")
        return api(method, path)

    with pytest.raises(ConnectionError):
        REFRESH.refresh("workflow_run", event(), REPO, unavailable, sleep=sleeps.append)
    assert api.writes == []


def test_write_denial_remains_a_failure():
    api = Api()

    def denied(method, path):
        if method == "POST":
            raise PermissionError("403")
        return api(method, path)

    with pytest.raises(PermissionError):
        REFRESH.refresh("workflow_run", event(), REPO, denied)


def test_relay_has_no_write_token_or_pr_checkout():
    relay_text = (ROOT / REFRESH.RELAY_PATH).read_text()
    privileged_text = (ROOT / ".github/workflows/pr-gates-refresh.yml").read_text()
    relay = yaml.load(relay_text, Loader=yaml.BaseLoader)
    privileged = yaml.load(privileged_text, Loader=yaml.BaseLoader)
    assert relay["permissions"] == {}
    assert set(relay["on"]) == REFRESH.RELAY_EVENTS
    assert relay["on"]["pull_request_review"]["types"] == ["submitted", "edited", "dismissed"]
    assert "secrets." not in relay_text
    assert all("uses" not in step for job in relay["jobs"].values() for step in job["steps"])
    assert privileged["on"]["workflow_run"]["workflows"] == [relay["name"]]
    assert privileged["jobs"]["refresh"]["timeout-minutes"] == "360"
    assert privileged["permissions"] == {"actions": "write", "contents": "read", "pull-requests": "read"}
    checkout = privileged["jobs"]["refresh"]["steps"][0]
    assert checkout["with"] == {
        "repository": "${{ github.repository }}",
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert "pull_request.head" not in privileged_text
    assert "download-artifact" not in privileged_text
