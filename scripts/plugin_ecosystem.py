"""独立模板、固定包元信息和维护期升级的一次本地闭环，不发布任何内容。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import tomllib
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.sdk.catalog import catalog_schema, source_digest, validate_entry
from neobot_modloader.sdk.storage import read_storage
from neobot_modloader.sdk.tooling import build_package, init_project
from neobot_modloader.sdk.tooling.upgrade_check import check_upgrade

if __package__:
    from .plugin_ci import run_pipeline
    from .plugin_compat import check_compatibility
    from .plugin_registry import accept_entry
else:
    from plugin_ci import run_pipeline
    from plugin_compat import check_compatibility
    from plugin_registry import accept_entry


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entry(source: Path, digest: str) -> dict:
    metadata = read_manifest(source / "plugin.toml")
    entry = {
        "schema_version": 1,
        "id": "local/" + metadata["name"],
        "name": metadata["name"],
        "version": metadata["version"],
        "sdk_api": 1,
        "status": "local",
        "source": {"tree_sha256": source_digest(source)},
        "artifact": {"sha256": digest},
        "compatibility": {"neobot": ">=2.0.2a11,<3", "python": ">=3.13,<3.15", "platforms": ["windows", "linux"]},
    }
    storage = read_storage(metadata)
    if storage is not None:
        entry["storage"] = asdict(storage)
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    return entry


def _history_preserved(report: dict) -> bool:
    data = Path(report["host"]) / "data/task_board"
    config = tomllib.loads((data / "config.toml").read_text(encoding="utf-8"))
    with closing(sqlite3.connect(data / "tasks.sqlite3")) as connection:
        rows = connection.execute("SELECT id, text FROM tasks ORDER BY id").fetchall()
    return config == {"caption": "历史工作清单"} and rows == [(1, "保留旧版任务")]


async def _accept_fixtures(template: Path, output: Path, reports: dict) -> tuple[dict[str, Path], dict[str, Path]]:
    """业务与升级历史作为测试夹具验收，不增加公开模板选项。"""
    projects: dict[str, Path] = {}
    packages: dict[str, Path] = {}
    for fixture, name in (
        ("command", "echo_plugin"),
        ("configured", "config_plugin"),
        ("managed", "todo_plugin"),
        ("page", "task_board"),
        ("legacy-managed", "task_board"),
    ):
        source = output / "projects" / fixture / name
        initialized = init_project(source, name, template=template / "fixtures/projects" / fixture)
        if not initialized.ok:
            raise ValueError("验收夹具初始化失败: " + "; ".join(initialized.errors))
        acceptance = await asyncio.to_thread(run_pipeline, source, output / "fixtures" / fixture)
        # 失败的阶段报告也要留下，不能因后续归档中断而丢失。
        reports[fixture] = acceptance
        if not acceptance["ok"]:
            raise ValueError(f"{fixture} 夹具实际验收失败")
        projects[fixture] = source
        artifact = acceptance["artifact"]
        package = output / "packages" / (artifact["sha256"] + ".zip")
        package.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact["path"], package)
        packages[fixture] = package
    return projects, packages


def _build_failure_package(template: Path, output: Path, failure: str) -> Path:
    """只修改新生成的合成夹具，分别模拟迁移中断和启动后写入失败。"""
    source = output / "projects" / (failure + "-failure") / "task_board"
    initialized = init_project(source, "task_board", template=template / "fixtures/projects/page")
    if not initialized.ok:
        raise ValueError("失败样本初始化失败")
    if failure == "migration":
        target = source / "migrations/data_1_2.py"
        content = '\n    raise RuntimeError("合成迁移失败")\n'
    else:
        target = source / "__init__.py"
        content = (
            "\n@plugin.on_startup\nasync def fail_startup(context):\n"
            '    with closing(sqlite3.connect(context.data_dir / "tasks.sqlite3")) as database, database:\n'
            "        database.execute(\"INSERT INTO tasks(title, done) VALUES ('候选启动写入', 0)\")\n"
            '    raise RuntimeError("合成启动失败")\n'
        )
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    package = output / (failure + "-failure.zip")
    built = build_package(source, package)
    if not built.ok:
        raise ValueError("失败样本打包失败: " + "; ".join(built.errors))
    return package


async def _check_failure_recovery(template: Path, output: Path, failure: str, previous: Path, fixture: Path) -> dict:
    """失败必须被拒绝且历史内容完整；启动失败还必须恢复旧包。"""
    package = _build_failure_package(template, output, failure)
    report = await check_upgrade(previous, package, fixture, output / (failure + "-failure"))
    preserved = _history_preserved(report)
    restored = failure == "migration" or report.get("upgrade", {}).get("restored") is True
    passed = not report["ok"] and preserved and restored
    return {
        "status": "passed" if passed else "failed",
        "history_preserved": preserved,
        "report": report,
    }


async def run_ecosystem(template: Path, registry: Path, output: Path) -> dict:
    """每次使用新的输出目录；保留合成宿主、包和报告供人工检查。"""
    output.mkdir(parents=True)
    result = {
        "schema_version": 1,
        "ok": False,
        "template": {},
        "fixtures": {},
        "errors": [],
        "unverified": [
            "github_actions",
            "other_environment_combinations",
            "real_services",
            "publisher_identity",
            "signature",
        ],
    }
    try:
        starter = output / "projects/starter/config_plugin"
        initialized = init_project(starter, "config_plugin", template=template)
        if not initialized.ok:
            raise ValueError("模板初始化失败: " + "; ".join(initialized.errors))
        result["template"] = await asyncio.to_thread(run_pipeline, starter, output / "template")
        if not result["template"]["ok"]:
            raise ValueError("默认模板实际验收失败")
        artifact = result["template"]["artifact"]
        package = output / "packages" / (artifact["sha256"] + ".zip")
        package.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact["path"], package)
        projects, packages = await _accept_fixtures(template, output, result["fixtures"])
        for source, artifact in (
            (starter, result["template"]["artifact"]),
            (projects["page"], result["fixtures"]["page"]["artifact"]),
        ):
            entry = _entry(source, artifact["sha256"])
            _write(registry / "local-candidates" / (entry["name"] + ".json"), entry)
        _write(registry / "schemas/plugin-entry.schema.json", catalog_schema())
        result["compatibility"] = await check_compatibility(
            registry, output / "packages", output / "compatibility", include_local=True
        )
        history = _entry(projects["legacy-managed"], result["fixtures"]["legacy-managed"]["artifact"]["sha256"])
        history["id"] = "local/task_board-history"
        _write(registry / "fixtures/history/task_board-0.1.0.json", history)
        result["history_compatibility"] = await accept_entry(history, packages["legacy-managed"], output / "history")
        fixture = template / "fixtures/task-board-upgrade.json"
        result["upgrade"] = await check_upgrade(
            packages["legacy-managed"], packages["page"], fixture, output / "upgrade"
        )
        result["failure_recovery"] = {}
        for failure in ("migration", "startup"):
            result["failure_recovery"][failure] = await _check_failure_recovery(
                template, output, failure, packages["legacy-managed"], fixture
            )
        result["ok"] = all(
            (
                result["compatibility"]["ok"],
                result["history_compatibility"]["ok"],
                result["upgrade"]["ok"],
                all(item["status"] == "passed" for item in result["failure_recovery"].values()),
            )
        )
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError, sqlite3.Error) as exc:
        result["errors"].append(str(exc))
    _write(output / "report.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用明确的本地 SDK 执行插件工程生态闭环")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = asyncio.run(run_ecosystem(args.template.resolve(), args.registry.resolve(), args.output.resolve()))
    print(
        json.dumps(
            {"ok": report["ok"], "errors": report["errors"], "report": str(args.output / "report.json")},
            ensure_ascii=True,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
