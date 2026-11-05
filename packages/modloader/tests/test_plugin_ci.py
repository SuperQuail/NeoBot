"""插件 CI 对真实工具结果、业务测试和失败阶段负责。"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import plugin_ci as ci
from scripts.plugin_ci_support import PipelineError, ProcessResult, pytest_summary, read_spec
from neobot_modloader.sdk.tooling import build_package, check_project, export_contract
from plugin_tooling_helpers import make_project


def project_with_tests(root: Path) -> Path:
    project = make_project(root)
    (project / "tests").mkdir()
    (project / "tests" / "test_sample.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")
    return project


def junit(path: Path, *, tests: int = 1, skipped: int = 0, failures: int = 0, errors: int = 0) -> None:
    path.write_text(
        f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" failures="{failures}" errors="{errors}">'
        + "<testcase name='sample'/>" * tests
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )


@pytest.fixture
def simulated_commands(monkeypatch):
    calls = []
    behavior = {"skip_tests": False, "smoke_digest": None, "timeout": None, "actual_tests": False, "frontend": None}

    def run(arguments: list[str], *, cwd: Path, log: Path, timeout: float) -> ProcessResult:
        calls.append((arguments, cwd))
        if behavior["timeout"] and any(behavior["timeout"] in argument for argument in arguments):
            return ProcessResult(-1, timed_out=True)
        if "neobot_modloader.sdk" in arguments:
            index = arguments.index("neobot_modloader.sdk")
            command = arguments[index + 1]
            project = Path(arguments[index + 2])
            if command == "check":
                report = check_project(project)
            elif command == "export":
                assert "--check" in arguments
                report = export_contract(project, check=True)
            elif command == "build":
                report = build_package(project, Path(arguments[arguments.index("--output") + 1]))
            else:
                from neobot_modloader.sdk.tooling.models import ToolReport
                import hashlib

                report = ToolReport(
                    "smoke",
                    True,
                    ("install", "start", "stop", "restart", "reload", "external_config"),
                    sha256=behavior["smoke_digest"] or hashlib.sha256(project.read_bytes()).hexdigest(),
                    executes_plugin=True,
                    unverified=("business_behavior", "database_migration", "real_services"),
                )
            log.write_text(json.dumps(report.to_dict()), encoding="utf-8")
            return ProcessResult(0 if report.ok else 1)
        if "--neobot-result-file" in arguments:
            if behavior["actual_tests"]:
                from scripts.plugin_ci_support import run_process

                return run_process(arguments, cwd=cwd, log=log, timeout=timeout)
            target = Path(arguments[arguments.index("--junitxml") + 1])
            junit(target, skipped=int(behavior["skip_tests"]))
            observed = Path(arguments[arguments.index("--neobot-result-file") + 1])
            observed.write_text(
                json.dumps(
                    {
                        "collected": 1,
                        "passed": int(not behavior["skip_tests"]),
                        "skipped": int(behavior["skip_tests"]),
                        "failures": 0,
                        "errors": 0,
                        "xfailed": 0,
                        "xpassed": 0,
                        "deselected": 0,
                        "exitstatus": 0,
                    }
                ),
                encoding="utf-8",
            )
        if "--prefix" in arguments:
            package = Path(arguments[arguments.index("--prefix") + 1]) / "node_modules" / "pnpm"
            (package / "bin").mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({"bin": {"pnpm": "bin/pnpm.mjs"}}), encoding="utf-8")
            (package / "bin" / "pnpm.mjs").write_text("// synthetic pnpm\n", encoding="utf-8")
        if arguments[-2:] == ["run", "build"] and behavior["frontend"]:
            web = behavior["frontend"] / "web"
            web.mkdir()
            (web / "index.html").write_text("<p>synthetic build</p>", encoding="utf-8")
        log.write_text("synthetic command output\n", encoding="utf-8")
        return ProcessResult(0)

    monkeypatch.setattr(ci, "run_process", run)
    return calls, behavior


def test_pipeline_accepts_only_the_final_package_and_records_unverified_scope(
    tmp_path: Path, simulated_commands
) -> None:
    project = project_with_tests(tmp_path)
    output = tmp_path / "acceptance"
    report = ci.run_pipeline(project, output)
    assert report["ok"] is True
    assert report["business_tests"]["collected"] == 1
    assert report["unverified"] == ["database_migration", "real_services"]
    assert report["artifact"]["sha256"] in (output / "SHA256SUMS").read_text(encoding="utf-8")
    assert report == json.loads((output / "report.json").read_text(encoding="utf-8"))
    names = [stage["name"] for stage in report["stages"]]
    assert names.index("static_contract") < names.index("export_contract") < names.index("business_tests")
    assert names.index("business_tests") < names.index("package") < names.index("smoke")


def test_pipeline_rejects_stale_contract_before_business_tests(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    entry = project / "__init__.py"
    entry.write_text(entry.read_text(encoding="utf-8") + "plugin.description = 'changed'\n", encoding="utf-8")
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["ok"] is False
    assert "business_behavior" in report["unverified"]
    assert not any("--neobot-result-file" in arguments for arguments, _ in simulated_commands[0])
    assert not report["artifact"]


def test_missing_business_tests_cannot_claim_acceptance(tmp_path: Path, simulated_commands) -> None:
    project = make_project(tmp_path)
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["ok"] is False
    assert "business_behavior" in report["unverified"]
    assert not report["artifact"]


def test_skipped_business_test_blocks_packaging(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    simulated_commands[1]["skip_tests"] = True
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["ok"] is False
    assert report["business_tests"]["skipped"] == 1
    assert not report["artifact"]
    assert not any("build" in arguments for arguments, _ in simulated_commands[0])


def test_dependency_requirements_are_passed_as_separate_arguments(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    manifest = project / "plugin.toml"
    manifest.write_text(
        'python_dependencies = ["httpx>=0.27,<0.29", "pydantic>=2,<3"]\n' + manifest.read_text(), encoding="utf-8"
    )
    assert ci.run_pipeline(project, tmp_path / "acceptance")["ok"]
    calls = [arguments for arguments, _ in simulated_commands[0]]
    install = next(arguments for arguments in calls if "install" in arguments)
    assert install[-3:] == ["--", "httpx>=0.27,<0.29", "pydantic>=2,<3"]
    assert install[install.index("--python") + 1] == sys.executable
    assert any(arguments[-2:] == ["--python", sys.executable] and "check" in arguments for arguments in calls)


@pytest.mark.parametrize("requirement", ["--index-url=https://bad.invalid", "-rrequirements.txt", "httpx\n--system"])
def test_dependency_options_cannot_be_inserted(tmp_path: Path, requirement: str) -> None:
    project = project_with_tests(tmp_path)
    manifest = project / "plugin.toml"
    manifest.write_text(
        "python_dependencies = [" + json.dumps(requirement) + "]\n" + manifest.read_text(), encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="python_dependencies"):
        read_spec(project)


def test_mismatched_smoke_digest_blocks_acceptance(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    simulated_commands[1]["smoke_digest"] = "0" * 64
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["ok"] is False
    assert not (tmp_path / "acceptance" / "SHA256SUMS").exists()


def test_timeout_is_a_failed_stage_and_blocks_following_work(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    simulated_commands[1]["timeout"] = "pytest"
    report = ci.run_pipeline(project, tmp_path / "acceptance", timeout=1)
    assert report["ok"] is False
    assert any(stage["status"] == "timed_out" for stage in report["stages"])
    assert not report["artifact"]


def test_output_must_not_change_the_package_input(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    with pytest.raises(PipelineError, match="output"):
        ci.run_pipeline(project, project / "artifacts")


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 3601])
def test_step_timeout_has_explicit_boundaries(tmp_path: Path, value: float, simulated_commands) -> None:
    with pytest.raises(PipelineError, match="timeout"):
        ci.run_pipeline(project_with_tests(tmp_path), tmp_path / "output", timeout=value)


@pytest.mark.parametrize("counts", [{"tests": 0}, {"skipped": 1}, {"failures": 1}, {"errors": 1}])
def test_junit_rejects_empty_skipped_failed_or_error_results(tmp_path: Path, counts: dict) -> None:
    path = tmp_path / "results.xml"
    junit(path, **counts)
    summary = pytest_summary(path)
    assert summary["ok"] is False


def test_process_timeout_cannot_return_success(tmp_path: Path) -> None:
    from scripts.plugin_ci_support import run_process

    result = run_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        log=tmp_path / "command.log",
        timeout=0.05,
    )
    assert result.timed_out
    assert result.returncode != 0


def test_cli_failure_writes_a_json_report_and_exits_nonzero(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    script = Path(__file__).resolve().parents[3] / "scripts" / "plugin_ci.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(project), "--output-dir", str(tmp_path / "output")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert completed.returncode != 0
    report = json.loads((tmp_path / "output" / "report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False


def test_explicit_nonstrict_xpass_cannot_claim_business_acceptance(tmp_path: Path, simulated_commands) -> None:
    project = project_with_tests(tmp_path)
    (project / "tests" / "test_sample.py").write_text(
        "import pytest\n@pytest.mark.xfail(reason='synthetic expected failure', strict=False)\n"
        "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )
    simulated_commands[1]["actual_tests"] = True
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["ok"] is False
    assert report["business_tests"]["xpassed"] == 1
    assert not report["artifact"]


def test_actual_passing_business_result_is_counted(tmp_path: Path, simulated_commands) -> None:
    simulated_commands[1]["actual_tests"] = True
    report = ci.run_pipeline(project_with_tests(tmp_path), tmp_path / "acceptance")
    assert report["ok"], report["errors"]
    assert report["business_tests"]["collected"] == report["business_tests"]["passed"] == 1


@pytest.mark.parametrize(
    ("statement", "problem"),
    [
        ("assert True", None),
        ("assert False", "failures"),
        ("pytest.skip('synthetic skip')", "skipped"),
        ("pytest.xfail('synthetic xfail')", "xfailed"),
    ],
)
def test_subtests_count_parent_items_and_preserve_child_outcomes(
    tmp_path: Path,
    simulated_commands,
    statement: str,
    problem: str | None,
) -> None:
    project = project_with_tests(tmp_path)
    (project / "tests" / "test_sample.py").write_text(
        "import pytest\ndef test_business(subtests):\n"
        "    with subtests.test(value=1):\n        assert True\n"
        f"    with subtests.test(value=2):\n        {statement}\n",
        encoding="utf-8",
    )
    simulated_commands[1]["actual_tests"] = True
    report = ci.run_pipeline(project, tmp_path / "acceptance")
    assert report["business_tests"]["collected"] == 1
    if problem is None:
        assert report["ok"], report["errors"]
        assert report["business_tests"]["passed"] == 1
        return
    assert report["ok"] is False
    assert report["business_tests"][problem] > 0
    assert report["business_tests"]["passed"] == 0
    assert not report["artifact"]


def test_timeout_terminates_ready_descendants_before_they_can_write(tmp_path: Path) -> None:
    from scripts.plugin_ci_support import run_process

    ready = tmp_path / "child-ready.txt"
    marker = tmp_path / "child-after-timeout.txt"
    child = (
        f"import time; from pathlib import Path; Path({str(ready)!r}).write_text('ready'); "
        f"time.sleep(1.5); Path({str(marker)!r}).write_text('continued')"
    )
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(10)"
    result = run_process(
        [sys._base_executable, "-c", parent],
        cwd=tmp_path,
        log=tmp_path / "timeout.log",
        timeout=1,
    )
    assert result.timed_out and ready.exists()
    time.sleep(1.6)
    assert not marker.exists()


def test_cancellation_terminates_ready_descendants(tmp_path: Path, monkeypatch) -> None:
    from scripts.plugin_ci_support import run_process

    ready = tmp_path / "child-ready.txt"
    marker = tmp_path / "child-after-cancel.txt"
    child = (
        f"import time; from pathlib import Path; Path({str(ready)!r}).write_text('ready'); "
        f"time.sleep(1.5); Path({str(marker)!r}).write_text('continued')"
    )
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(10)"
    original_wait = subprocess.Popen.wait
    interrupted = False

    def wait(process, timeout=None):
        nonlocal interrupted
        if interrupted:
            return original_wait(process, timeout=timeout)
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        interrupted = True
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    with pytest.raises(KeyboardInterrupt):
        run_process([sys._base_executable, "-c", parent], cwd=tmp_path, log=tmp_path / "cancel.log", timeout=10)
    assert ready.exists()
    time.sleep(1.6)
    assert not marker.exists()


def test_pipeline_cancellation_is_not_success(tmp_path: Path, monkeypatch) -> None:
    def cancelled(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ci, "run_process", cancelled)
    report = ci.run_pipeline(project_with_tests(tmp_path), tmp_path / "output")
    assert report["ok"] is False
    assert any(stage["status"] == "cancelled" for stage in report["stages"])


def test_python_pipeline_does_not_look_for_node(tmp_path: Path, simulated_commands, monkeypatch) -> None:
    def unexpected_lookup(name):
        raise AssertionError(f"Python 工程不应探测 {name}")

    monkeypatch.setattr(ci.shutil, "which", unexpected_lookup)
    assert ci.run_pipeline(project_with_tests(tmp_path), tmp_path / "output")["ok"]


def test_frontend_build_precedes_page_check_and_avoids_cmd_shims(
    tmp_path: Path, simulated_commands, monkeypatch
) -> None:
    project = project_with_tests(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@12.3.4",
                "scripts": {"verify": "check", "build": "build"},
            }
        ),
        encoding="utf-8",
    )
    (frontend / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    manifest = project / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + 'pages=["web/index.html"]\n[sdk.frontend]\npath="frontend"\n',
        encoding="utf-8",
    )
    node = tmp_path / "node.exe"
    npm = tmp_path / ("npm.cmd" if os.name == "nt" else "npm")
    npm_entry = npm.parent / "node_modules" / "npm" / "bin" / "npm-cli.js" if os.name == "nt" else npm
    npm_entry.parent.mkdir(parents=True, exist_ok=True)
    npm_entry.write_text("// synthetic npm\n", encoding="utf-8")
    monkeypatch.setattr(ci.shutil, "which", lambda name: str(node) if name == "node" else str(npm))
    simulated_commands[1]["frontend"] = project
    report = ci.run_pipeline(project, tmp_path / "with & space")
    assert report["ok"], report["errors"]
    calls = [arguments for arguments, _ in simulated_commands[0]]
    build = next(index for index, arguments in enumerate(calls) if arguments[-2:] == ["run", "build"])
    static = next(
        index for index, arguments in enumerate(calls) if "neobot_modloader.sdk" in arguments and "check" in arguments
    )
    assert build < static
    pnpm_calls = [arguments for arguments in calls if arguments[-2:] in (["run", "verify"], ["run", "build"])]
    assert all(arguments[0] == str(node) and arguments[1].endswith("pnpm.mjs") for arguments in pnpm_calls)
    assert not any(argument.endswith(".cmd") for arguments in calls for argument in arguments)
