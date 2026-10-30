"""对元信息中的固定插件包逐个重做当前环境兼容验收。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from neobot_modloader.installer import PluginInstaller
from neobot_modloader.sdk.catalog import load_catalog

if __package__:
    from .plugin_registry import accept_entry
else:
    from plugin_registry import accept_entry


async def check_compatibility(
    repository: Path,
    packages: Path,
    output: Path,
    *,
    include_local: bool = False,
    download: bool = False,
    timeout: float = 300.0,
) -> dict:
    """本地按 SHA 查找包；正式 CI 可下载已登记的公开 HTTPS 包。"""
    output.mkdir(parents=True, exist_ok=True)
    packages.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "ok": False,
        "status": "failed",
        "results": [],
        "errors": [],
        "unverified": ["other_environment_combinations", "real_services"],
    }
    try:
        entries = load_catalog(repository, include_local=include_local)
        if not entries:
            raise ValueError("目录没有需要验收的条目，不能声明兼容检查通过")
        downloader = PluginInstaller(plugin_dir=output / "download-unused")
        for entry in entries:
            package = packages / (entry["artifact"]["sha256"] + ".zip")
            needs_download = not package.is_file() and download
            if needs_download and entry["status"] != "published":
                raise ValueError("本地未发布候选必须显式提供固定包，不能自动下载")
            if needs_download:
                archive = await downloader._fetch_bytes(entry["artifact"]["url"])
                package.write_bytes(archive)
            report = await accept_entry(entry, package, output / entry["id"].replace("/", "--"), timeout=timeout)
            result["results"].append(report)
        result["ok"] = all(report["ok"] for report in result["results"])
        result["status"] = "passed" if result["ok"] else "failed"
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError) as exc:
        result["errors"].append(str(exc))
    (output / "compatibility.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对登记的最终包执行当前 SDK 的受控兼容检查")
    parser.add_argument("repository", type=Path)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-local", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--timeout", type=float, default=300.0)
    arguments = parser.parse_args(argv)
    report = asyncio.run(
        check_compatibility(
            arguments.repository,
            arguments.packages,
            arguments.output,
            include_local=arguments.include_local,
            download=arguments.download,
            timeout=arguments.timeout,
        )
    )
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
