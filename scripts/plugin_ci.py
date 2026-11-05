"""作者本地与无凭据 CI 共用的插件验收入口，不执行发布。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from neobot_modloader.sdk.tooling.files import safe_file

if __package__:
    from .plugin_ci_support import (
        SUPPORTED_PYTHON,
        PipelineError,
        ProcessResult,
        ProjectSpec,
        interpreter_supported,
        pytest_summary,
        read_spec,
        run_process,
        validate_timeout,
    )
else:
    from plugin_ci_support import (
        SUPPORTED_PYTHON,
        PipelineError,
        ProcessResult,
        ProjectSpec,
        interpreter_supported,
        pytest_summary,
        read_spec,
        run_process,
        validate_timeout,
    )

SDK_ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "static_declarations",
    "python_dependencies",
    "dependency_check",
    "frontend",
    "static_contract",
    "export_contract",
    "business_tests",
    "package",
    "determinism",
    "smoke",
)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class _Pipeline:
    def __init__(self, project: Path, output: Path, timeout: float) -> None:
        self.output = output
        self.timeout = timeout
        self.current: dict | None = None
        self.report = {
            "schema_version": 1,
            "ok": False,
            "project": str(project),
            "python": sys.version.split()[0],
            "supported_python": list(SUPPORTED_PYTHON),
            "step_timeout_seconds": timeout,
            "stages": [{"name": name, "status": "blocked"} for name in STAGES],
            "business_tests": {},
            "artifact": None,
            "errors": [],
            "unverified": ["business_behavior", "database_migration", "real_services"],
        }

    def stage(self, name: str) -> dict:
        stage = next(item for item in self.report["stages"] if item["name"] == name)
        self.current = stage
        return stage

    def command(
        self, name: str, arguments: list[str], *, cwd: Path = SDK_ROOT, allow_failure: bool = False
    ) -> ProcessResult:
        stage = self.stage(name)
        log = self.output / f"{name}.log"
        stage["log"] = str(log)
        started = time.monotonic()
        result = run_process(arguments, cwd=cwd, log=log, timeout=self.timeout)
        stage["duration_seconds"] = round(time.monotonic() - started, 3)
        stage["returncode"] = result.returncode
        stage["status"] = "passed" if result.returncode == 0 else "failed"
        if result.timed_out:
            stage["status"] = "timed_out"
        if result.timed_out or (result.returncode != 0 and not allow_failure):
            raise PipelineError(f"{name} 失败，详情见 {log.name}")
        return result

    def sdk(self, name: str, command: str, path: Path, *options: str, required: tuple[str, ...]) -> dict:
        result = self.command(
            name,
            [sys.executable, "-m", "neobot_modloader.sdk", command, str(path), *options, "--json"],
            allow_failure=True,
        )
        try:
            log = self.output / f"{name}.log"
            if log.stat().st_size > 1024 * 1024:
                raise ValueError("报告过大")
            report = json.loads(log.read_text(encoding="utf-8-sig"))
            if not isinstance(report, dict) or report.get("command") != command:
                raise ValueError("报告命令不一致")
            checks = report.get("checks")
            if not isinstance(checks, list) or any(not isinstance(item, str) for item in checks):
                raise ValueError("缺少检查结果")
            if not isinstance(report.get("errors"), list):
                raise ValueError("缺少错误列表")
        except (OSError, ValueError) as exc:
            raise PipelineError(f"{name} 未产生有效工具报告: {exc}") from None
        self.current["tool_report"] = report
        if result.returncode != 0 or report.get("ok") is not True:
            raise PipelineError(f"{name}: " + "; ".join(str(error) for error in report["errors"]))
        if not set(required).issubset(checks):
            raise PipelineError(f"{name} 缺少必须完成的检查")
        if command in {"export", "smoke"} and report.get("executes_plugin") is not True:
            raise PipelineError(f"{name} 没有执行插件验收")
        return report

    def frontend(self, spec: ProjectSpec) -> None:
        self.stage("frontend")
        if spec.frontend is None:
            self.stage("frontend")["status"] = "not_applicable"
            return
        node = shutil.which("node")
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if node is None or npm is None:
            raise PipelineError("声明了前端工程，需要先安装 Node.js")
        npm_entry = Path(npm).resolve()
        if os.name == "nt":
            npm_entry = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if not npm_entry.is_file():
            raise PipelineError("npm 的 JavaScript 入口不存在，请检查 Node.js 安装")
        tools = self.output / "toolchain"
        self.command(
            "frontend",
            [
                node,
                str(npm_entry),
                "install",
                "--prefix",
                str(tools),
                "--no-package-lock",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                spec.package_manager,
            ],
        )
        package = tools / "node_modules" / "pnpm"
        try:
            manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
            pnpm = safe_file(package, manifest["bin"]["pnpm"], label="pnpm.bin")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PipelineError("锁定的 pnpm 安装后没有有效入口") from exc
        executable = [node, str(pnpm)] if pnpm.suffix in {".js", ".cjs", ".mjs"} else [str(pnpm)]
        for arguments in (["install", "--frozen-lockfile"], ["run", "verify"], ["run", "build"]):
            # 每个子步骤都有独立日志，前一步成功也不能掩盖后一步失败。
            name = "frontend_" + arguments[-1].replace("--", "")
            temporary = self.output / f"{name}.log"
            result = run_process([*executable, *arguments], cwd=spec.frontend, log=temporary, timeout=self.timeout)
            self.current.setdefault("commands", []).append({"log": str(temporary), "returncode": result.returncode})
            if result.returncode != 0 or result.timed_out:
                self.current["status"] = "timed_out" if result.timed_out else "failed"
                raise PipelineError(f"{name} 失败")

    def run(self, project: Path, config: Path | None) -> None:
        stage = self.stage("static_declarations")
        if not interpreter_supported():
            raise PipelineError("当前公开支持的 Python 版本为 3.13、3.14")
        spec = read_spec(project)
        self.report["business_suite"] = spec.tests.relative_to(project).as_posix()
        stage["status"] = "passed"
        if spec.dependencies:
            self.command(
                "python_dependencies", ["uv", "pip", "install", "--python", sys.executable, "--", *spec.dependencies]
            )
        else:
            self.stage("python_dependencies")["status"] = "not_applicable"
        self.command("dependency_check", ["uv", "pip", "check", "--python", sys.executable])
        self.frontend(spec)
        self.sdk("static_contract", "check", project, required=("entry", "manifest", "files", "contract"))
        self.sdk("export_contract", "export", project, "--check", required=("contract",))
        xml = self.output / "pytest.xml"
        execution = self.output / "pytest-execution.json"
        result = self.command(
            "business_tests",
            [
                sys.executable,
                str(SDK_ROOT / "scripts" / "plugin_ci_pytest.py"),
                str(spec.tests),
                "--junitxml",
                str(xml),
                "--neobot-result-file",
                str(execution),
                "--strict-markers",
                "-o",
                "addopts=",
                "-o",
                "xfail_strict=true",
                "-p",
                "no:cacheprovider",
                "-q",
            ],
            cwd=project,
            allow_failure=True,
        )
        self.report["business_tests"] = pytest_summary(xml, execution=execution)
        if result.returncode != 0 or not self.report["business_tests"]["ok"]:
            raise PipelineError("业务 pytest 必须收集至少一个用例，且不能存在失败、错误、跳过、xfail 或 xpass")
        self.report["unverified"].remove("business_behavior")
        package = self.output / "plugin.zip"
        built = self.sdk("package", "build", project, "--output", str(package), required=("archive",))
        package_hash = digest(package)
        if built.get("sha256") != package_hash:
            raise PipelineError("build 报告摘要与最终 ZIP 不一致")
        self.report["artifact"] = {"path": str(package), "sha256": package_hash}
        with tempfile.TemporaryDirectory(prefix="rebuild-", dir=self.output) as directory:
            rebuilt = Path(directory) / "plugin.zip"
            report = self.sdk("determinism", "build", project, "--output", str(rebuilt), required=("archive",))
            if report.get("sha256") != package_hash or digest(rebuilt) != package_hash:
                raise PipelineError("两次独立构建的 ZIP 摘要不一致")
        options = ["--timeout", str(min(30.0, self.timeout * 0.8))]
        if config is not None:
            options.extend(["--config", str(config)])
        smoke = self.sdk(
            "smoke", "smoke", package, *options, required=("install", "start", "stop", "restart", "external_config")
        )
        if "reload" not in smoke["checks"] and "reload" not in smoke.get("not_applicable", []):
            raise PipelineError("smoke 未说明 reload 验收结果")
        if smoke.get("sha256") != package_hash or digest(package) != package_hash:
            raise PipelineError("smoke 验收的 ZIP 摘要与打包产物不一致")
        (self.output / "SHA256SUMS").write_text(f"{package_hash}  plugin.zip\n", encoding="utf-8", newline="\n")


def run_pipeline(project: Path, output_dir: Path, *, config: Path | None = None, timeout: float = 300.0) -> dict:
    """完整验收返回 JSON 报告；只有可选能力允许 not_applicable。"""
    validate_timeout(timeout)
    project = project.resolve()
    output = output_dir.resolve()
    if output.is_relative_to(project):
        raise PipelineError("output 必须位于插件源码目录之外")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "plugin.zip", "SHA256SUMS", "pytest.xml", "pytest-execution.json"):
        (output / name).unlink(missing_ok=True)
    pipeline = _Pipeline(project, output, timeout)
    try:
        pipeline.run(project, config.resolve() if config is not None else None)
        pipeline.report["ok"] = all(
            stage["status"] in {"passed", "not_applicable"} for stage in pipeline.report["stages"]
        )
    except KeyboardInterrupt:
        if pipeline.current is not None:
            pipeline.current["status"] = "cancelled"
        pipeline.report["errors"].append("验收已取消")
    except (PipelineError, OSError, ValueError) as exc:
        if pipeline.current is not None and pipeline.current["status"] != "timed_out":
            pipeline.current["status"] = "failed"
        pipeline.report["errors"].append(str(exc))
    (output / "report.json").write_text(
        json.dumps(pipeline.report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return pipeline.report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="执行与插件 CI 相同的静态、业务、打包及安装验收")
    parser.add_argument("project", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config", type=Path, help="仅使用合成 TOML 配置样例")
    parser.add_argument("--timeout", type=float, default=300.0, help="每个子进程的超时秒数，上限 3600")
    parser.add_argument("--plan", action="store_true", help="仅静态读取工程声明，供 CI 决定是否安装 Node")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--template-name", help="先在不存在的 project 路径生成 SDK 模板")
    arguments = parser.parse_args(argv)
    try:
        if arguments.template_name:
            from neobot_modloader.sdk.tooling import init_project

            report = init_project(arguments.project, arguments.template_name)
            if not report.ok:
                raise PipelineError("; ".join(report.errors))
        if arguments.plan:
            spec = read_spec(arguments.project)
            if arguments.github_output:
                with arguments.github_output.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(f"frontend={'true' if spec.frontend is not None else 'false'}\n")
            print(json.dumps({"project": str(spec.root), "frontend": spec.frontend is not None}))
            return 0
        if arguments.output_dir is None:
            parser.error("完整验收必须提供 --output-dir")
        report = run_pipeline(
            arguments.project, arguments.output_dir, config=arguments.config, timeout=arguments.timeout
        )
    except (PipelineError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
