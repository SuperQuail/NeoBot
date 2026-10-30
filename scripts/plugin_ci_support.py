"""插件验收共用的声明读取、子进程边界与业务测试结果解析。"""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from neobot_modloader.loading.manifest import read_manifest, read_python_dependencies
from neobot_modloader.plugins.registration import validate_plugin_name
from neobot_modloader.sdk.tooling.files import safe_file
from neobot_modloader.sdk.tooling.frontend import read_frontend
from neobot_modloader.sdk.tooling.validation import contract_path
from neobot_modloader.sdk.tooling.suite import read_test_suite

if __package__:
    from .plugin_ci_process import ProcessTree
else:
    from plugin_ci_process import ProcessTree

SUPPORTED_PYTHON = ("3.13", "3.14")


class PipelineError(ValueError):
    """验收流程可定位、可写入机器报告的失败。"""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    timed_out: bool = False


@dataclass(frozen=True)
class ProjectSpec:
    root: Path
    dependencies: tuple[str, ...]
    frontend: Path | None
    package_manager: str | None
    tests: Path


def validate_timeout(timeout: float) -> None:
    if not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise PipelineError("timeout 必须在 0 到 3600 秒之间")


def read_spec(path: Path) -> ProjectSpec:
    """构建前只校验声明与源码语法，页面是否存在留给构建后的 check。"""
    root = path.resolve()
    try:
        if not root.is_dir():
            raise PipelineError("插件工程目录不存在")
        manifest = safe_file(root, "plugin.toml", label="plugin.toml")
        metadata = read_manifest(manifest)
        validate_plugin_name(metadata.get("name"))
        sdk = metadata.get("sdk")
        if not isinstance(sdk, dict) or type(sdk.get("version")) is not int or sdk["version"] != 1:
            raise PipelineError("统一验收需要 sdk.version = 1")
        contract_path(root, metadata)
        entry = safe_file(root, "__init__.py", label="entry")
        ast.parse(entry.read_text(encoding="utf-8-sig"), filename=str(entry))
        dependencies = read_python_dependencies(metadata)
        for index, requirement in enumerate(dependencies):
            if any(character in requirement for character in ("\n", "\r", "\0")):
                raise PipelineError(f"python_dependencies[{index}]: 需求中不能包含换行或 NUL")
            try:
                Requirement(requirement)
            except InvalidRequirement as exc:
                raise PipelineError(f"python_dependencies[{index}]: 必须是 PEP 508 需求") from exc
        frontend = read_frontend(root, metadata)
        manager = None
        if frontend is not None:
            manager = json.loads((frontend / "package.json").read_text(encoding="utf-8-sig"))["packageManager"]
        tests = read_test_suite(root, metadata, required=True)
        return ProjectSpec(root, dependencies, frontend, manager, tests)
    except (OSError, ValueError, TypeError, SyntaxError) as exc:
        raise PipelineError(str(exc)) from None


def run_process(arguments: list[str], *, cwd: Path, log: Path, timeout: float) -> ProcessResult:
    """使用参数列表，作者声明不会经 shell 再解释。超时必须返回失败。"""
    environment = os.environ.copy()
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        PYTHONNOUSERSITE="1",
        PYTHONIOENCODING="utf-8",
        PYTEST_ADDOPTS="",
    )
    try:
        with (
            log.open("w", encoding="utf-8", newline="\n") as handle,
            log.with_suffix(".stderr.log").open("w", encoding="utf-8", newline="\n") as errors,
        ):
            tree = ProcessTree()
            process = None
            try:
                process = subprocess.Popen(
                    arguments,
                    cwd=cwd,
                    env=environment,
                    stdout=handle,
                    stderr=errors,
                    **tree.popen_options(),
                )
                tree.attach(process)
                return ProcessResult(process.wait(timeout=timeout))
            finally:
                tree.close(process)
    except subprocess.TimeoutExpired:
        with log.open("a", encoding="utf-8") as handle:
            handle.write("\n插件验收子进程超时\n")
        return ProcessResult(-1, timed_out=True)
    except OSError as exc:
        log.write_text(str(exc), encoding="utf-8")
        return ProcessResult(-1)


def pytest_summary(path: Path, *, execution: Path | None = None) -> dict:
    """JUnit 中跳过与 xfail 都属于未运行，至少一个完整成功用例才可通过。"""
    try:
        root = ET.parse(path).getroot()
        suites = [node for node in root.iter("testsuite") if node.find("testsuite") is None]
        cases = list(root.iter("testcase"))
        totals = {
            name: sum(int(suite.get(name, "0")) for suite in suites)
            for name in ("tests", "errors", "failures", "skipped")
        }
    except (OSError, ValueError, ET.ParseError) as exc:
        raise PipelineError("pytest 没有产生有效 JUnit 报告") from exc
    if any(value < 0 for value in totals.values()):
        raise PipelineError("pytest JUnit 统计无效")
    for name in ("errors", "failures", "skipped"):
        child_name = {"errors": "error", "failures": "failure", "skipped": "skipped"}[name]
        totals[name] = max(totals[name], sum(case.find(child_name) is not None for case in cases))
    collected = len(cases)
    passed = max(0, collected - totals["skipped"] - totals["errors"] - totals["failures"])
    stats = {
        "collected": collected,
        "passed": passed,
        **{key: totals[key] for key in ("skipped", "failures", "errors")},
    }
    stats.update(xfailed=0, xpassed=0, deselected=0)
    if execution is None:
        return {"ok": False, **stats}
    try:
        observed = json.loads(execution.read_text(encoding="utf-8"))
        if not isinstance(observed, dict) or type(observed.get("exitstatus")) is not int:
            raise ValueError("执行结果无效")
        if any(type(observed.get(key)) is not int or observed[key] < 0 for key in stats):
            raise ValueError("执行统计无效")
    except (OSError, ValueError) as exc:
        raise PipelineError("pytest 没有产生宿主执行结果") from exc
    stats = {key: max(value, observed[key]) for key, value in stats.items()}
    stats["collected"] = observed["collected"]
    stats["passed"] = observed["passed"]
    # pytest 9 的 JUnit tests 包含成功子报告，父项数以宿主 hook 和 testcase 为准。
    complete = observed["collected"] == collected == observed["passed"]
    no_partial = not any(stats[key] for key in ("skipped", "failures", "errors", "xfailed", "xpassed", "deselected"))
    return {"ok": collected > 0 and complete and no_partial and observed.get("exitstatus") == 0, **stats}


def interpreter_supported() -> bool:
    return f"{sys.version_info.major}.{sys.version_info.minor}" in SUPPORTED_PYTHON
