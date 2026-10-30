"""新增插件工作流的执行来源、凭据边界与必需矩阵回归。"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def workflow(name: str) -> dict:
    # GitHub 使用 YAML 1.2；BaseLoader 避免 YAML 1.1 将 on 读成布尔键。
    return yaml.load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


@pytest.mark.parametrize("name", ["plugin-ci.yml", "plugin-sdk-validation.yml"])
def test_workflows_have_read_only_permissions_pinned_actions_and_no_bypass(name: str) -> None:
    document = workflow(name)
    assert document["permissions"] == {"contents": "read"}
    assert not {"pull_request_target", "workflow_run"}.intersection(document["on"])
    for job in document["jobs"].values():
        assert "secrets" not in job
        assert "continue-on-error" not in job
        for step in job.get("steps", []):
            assert "continue-on-error" not in step
            assert "${{ inputs." not in step.get("run", "")
            reference = step.get("uses", "")
            if not reference:
                continue
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference)
            if reference.startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"


def test_reusable_workflow_uses_current_caller_commit_and_fixed_sdk_repository() -> None:
    document = workflow("plugin-ci.yml")
    job = document["jobs"]["acceptance"]
    assert job["strategy"]["matrix"] == {"os": ["ubuntu-latest", "windows-latest"], "python": ["3.13", "3.14"]}
    checkouts = [step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
    assert checkouts[0]["with"]["repository"] == "${{ github.repository }}"
    assert checkouts[0]["with"]["ref"] == "${{ github.sha }}"
    assert checkouts[1]["with"]["repository"] == "SuperQuail/NeoBot"
    assert checkouts[1]["with"]["ref"] == "${{ inputs.sdk-ref }}"
    assert any(
        "uv sync --package neobot-modloader --locked" in step.get("run", "")
        and "uv sync --only-group dev --inexact --locked" in step.get("run", "")
        for step in job["steps"]
    )
    node = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-node@"))
    assert node["if"] == "steps.plan.outputs.frontend == 'true'"


def bootstrap(tmp_path: Path, **values: str) -> subprocess.CompletedProcess:
    step = workflow("plugin-ci.yml")["jobs"]["acceptance"]["steps"][0]
    environment = os.environ.copy()
    environment.update(
        SDK_REF="a" * 40,
        PLUGIN_PATH=".",
        CONFIG_PATH="",
        GENERATE_TEMPLATE="false",
        GITHUB_WORKSPACE=str(tmp_path),
        RUNNER_TEMP=str(tmp_path / "temporary"),
        GITHUB_ENV=str(tmp_path / "environment"),
        PYTHONIOENCODING="utf-8",
    )
    environment.update(values)
    return subprocess.run(
        [sys.executable, "-c", step["run"]],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize("revision", ["dev", "v1.0.0", "a" * 39, "a" * 40 + "\n"])
def test_reusable_workflow_rejects_floating_or_invalid_sdk_ref(tmp_path: Path, revision: str) -> None:
    assert bootstrap(tmp_path, SDK_REF=revision).returncode != 0
    assert not (tmp_path / "environment").exists()


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:/outside", "test\\other", "test\nOTHER=value"])
def test_reusable_workflow_rejects_path_escape_or_environment_injection(tmp_path: Path, path: str) -> None:
    assert bootstrap(tmp_path, PLUGIN_PATH=path).returncode != 0
    assert not (tmp_path / "environment").exists()


def test_reusable_workflow_resolves_caller_project_without_shell_interpolation(tmp_path: Path) -> None:
    assert bootstrap(tmp_path, PLUGIN_PATH="plugins/my sample").returncode == 0
    assert f"NEOBOT_PLUGIN_PROJECT={tmp_path / 'plugin' / 'plugins' / 'my sample'}" in (
        tmp_path / "environment"
    ).read_text(encoding="utf-8")


def test_host_workflow_runs_the_template_and_real_browser_with_required_aggregate() -> None:
    jobs = workflow("plugin-sdk-validation.yml")["jobs"]
    assert jobs["template"]["uses"] == "./.github/workflows/plugin-ci.yml"
    assert jobs["template"]["with"] == {"sdk-ref": "${{ github.sha }}", "generate-template": "true"}
    browser_commands = [step.get("run", "") for step in jobs["browser"]["steps"]]
    assert any("pnpm run verify" in command and "pnpm run build" in command for command in browser_commands)
    assert any("playwright install --with-deps chromium" in command for command in browser_commands)
    assert any("test_plugin_workbench_browser.py -m browser" in command for command in browser_commands)
    assert any(
        "test_plugin_hot_reload_browser.py -m browser" in command and "plugin-browser-hot-reload.xml" in command
        for command in browser_commands
    )
    assert any("test_plugin_views_api.py -m browser" in command for command in browser_commands)
    assert jobs["verified"]["needs"] == ["template", "sdk", "browser"]
    assert jobs["verified"]["if"] == "always()"
