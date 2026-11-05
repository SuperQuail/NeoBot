"""受控插件入库验收与兼容报告；不发布、不签名、不读取作者自报结论。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import tempfile
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from packaging.specifiers import SpecifierSet

from neobot_modloader.installer import MAX_ARCHIVE_BYTES, PluginInstaller
from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.sdk.catalog import catalog_schema, load_catalog, source_digest, validate_entry
from neobot_modloader.sdk.storage import read_storage
from neobot_modloader.sdk.tooling import smoke_package

if __package__:
    from .plugin_ci import run_pipeline
else:
    from plugin_ci import run_pipeline

SDK_ROOT = Path(__file__).resolve().parents[1]


def _tool_digest() -> str:
    digest = hashlib.sha256()
    paths = sorted((SDK_ROOT / "packages/modloader/src").rglob("*.py"))
    paths.extend(sorted((SDK_ROOT / "scripts").glob("plugin_*.py")))
    for path in paths:
        digest.update(path.relative_to(SDK_ROOT).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _read_candidate_archive(entry: dict, package: Path) -> tuple[bytes, str]:
    """校验登记条目和最终包身份，不执行包内代码。"""
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    if not package.is_file() or package.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("最终 ZIP 不存在或超过安装器体积上限")
    archive = package.read_bytes()
    # 文件可能在 stat 后增长，读取完成后仍须检查实际字节数。
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("最终 ZIP 超过安装器体积上限")
    digest = hashlib.sha256(archive).hexdigest()
    if digest != entry["artifact"]["sha256"]:
        raise ValueError("最终 ZIP 摘要与元信息不一致")
    return archive, digest


def _check_environment(entry: dict, environment: dict) -> None:
    """只接受本次实际运行的宿主、Python 和平台组合。"""
    compatibility = entry["compatibility"]
    for name in ("neobot", "python"):
        if not SpecifierSet(compatibility[name]).contains(environment[name], prereleases=True):
            raise ValueError(f"当前 {name} 不在声明兼容范围")
    if environment["platform"] not in compatibility["platforms"]:
        raise ValueError("当前平台不在声明兼容范围")


def _check_installed_metadata(entry: dict, installed: Path) -> str:
    """从安装后的文件重读元信息，返回实际源码树摘要。"""
    metadata = read_manifest(installed / "plugin.toml")
    version_matches = metadata.get("version") == entry["version"]
    sdk_matches = metadata.get("sdk", {}).get("version") == entry["sdk_api"]
    if not version_matches or not sdk_matches:
        raise ValueError("包内版本或 SDK API 与元信息不一致")
    storage = read_storage(metadata)
    actual_storage = asdict(storage) if storage is not None else None
    if actual_storage != entry.get("storage"):
        raise ValueError("包内配置/数据版本与元信息不一致")
    actual_source = source_digest(installed)
    expected_source = entry["source"].get("tree_sha256")
    if expected_source is not None and expected_source != actual_source:
        raise ValueError("包内源码树摘要与元信息不一致")
    return actual_source


async def accept_entry(entry: dict, package: Path, output: Path, *, timeout: float = 300.0) -> dict:
    """先核对固定包，再由宿主工具重做验收；环境范围只记录实际跑过的组合。"""
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "ok": False,
        "id": entry.get("id") if isinstance(entry, dict) else None,
        "checks": [],
        "errors": [],
        "environment": {
            "neobot": version("neobot-modloader"),
            "python": platform.python_version(),
            "platform": {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
                platform.system(), platform.system().lower()
            ),
        },
        "tool": {"source_tree_sha256": _tool_digest(), "published": False},
        "unverified": ["other_environment_combinations", "real_services", "publisher_identity", "signature"],
    }
    try:
        archive, digest = _read_candidate_archive(entry, package)
        report["artifact"] = {"sha256": digest, "path": str(package.resolve())}
        report["checks"].append("artifact_identity")
        _check_environment(entry, report["environment"])
        report["checks"].append("environment")
        # 安装后的元信息读取与受控重建都必须在临时源码目录存活期间完成。
        with tempfile.TemporaryDirectory(prefix="neobot-registry-") as temporary:

            async def fetcher(url: str) -> bytes:
                return archive

            installer = PluginInstaller(plugin_dir=Path(temporary) / "plugins", fetcher=fetcher)
            installed = await installer.install("registry/candidate", expected_name=entry["name"])
            if not installed.ok or installed.path is None:
                raise ValueError(f"安装固定包失败: {installed.error}")
            report["source_tree_sha256"] = _check_installed_metadata(entry, installed.path)
            report["checks"].append("package_metadata")
            controlled = await asyncio.to_thread(run_pipeline, installed.path, output / "controlled", timeout=timeout)
            report["controlled"] = controlled
            if not controlled["ok"]:
                raise ValueError("受控业务/工程验收失败")
            if controlled["artifact"]["sha256"] != digest:
                raise ValueError("受控重建改变最终 ZIP，不能放行另一个包")
            report["checks"].append("controlled_acceptance")
        smoke = await smoke_package(package, timeout=min(timeout, 30.0))
        report["input_package_smoke"] = smoke.to_dict()
        if not smoke.ok or smoke.sha256 != digest:
            raise ValueError("输入最终 ZIP 的独立安装冒烟失败")
        report["checks"].append("input_package_smoke")
        report["ok"] = True
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError) as exc:
        report["errors"].append(str(exc))
    (output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查独立插件元信息仓库和固定候选包")
    commands = parser.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("schema")
    schema.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("repository", type=Path)
    check.add_argument("--include-local", action="store_true")
    accept = commands.add_parser("accept")
    accept.add_argument("entry", type=Path)
    accept.add_argument("package", type=Path)
    accept.add_argument("--output", type=Path, required=True)
    accept.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.command == "schema":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(catalog_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    if args.command == "check":
        items = load_catalog(args.repository, include_local=args.include_local)
        print(
            json.dumps(
                {"ok": True, "entries": len(items), "published": sum(item["status"] == "published" for item in items)}
            )
        )
        return 0
    report = asyncio.run(
        accept_entry(
            json.loads(args.entry.read_text(encoding="utf-8")), args.package, args.output, timeout=args.timeout
        )
    )
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
