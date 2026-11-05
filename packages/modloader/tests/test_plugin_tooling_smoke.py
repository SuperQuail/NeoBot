"""最终 ZIP 经真实安装器和运行时验收，不能以源码导入冒充安装。"""

import asyncio
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from neobot_modloader.sdk.tooling import build_package, smoke_package
from plugin_tooling_helpers import make_project


async def test_smoke_installs_the_built_zip_and_checks_external_config(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    package = build_package(path, tmp_path / "plugin.zip")
    assert package.ok, package.errors
    with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network forbidden")):
        report = await smoke_package(Path(package.path))
    assert report.ok, report.errors
    assert report.sha256 == package.sha256
    assert report.executes_plugin is True
    assert {"install", "start", "stop", "restart", "reload", "external_config"}.issubset(report.checks)


async def test_smoke_reports_startup_failure_and_cleans_modules(tmp_path: Path) -> None:
    path = make_project(
        tmp_path,
        body="\n@plugin.on_startup\nasync def start(ctx):\n    raise RuntimeError('synthetic startup failure')\n",
    )
    package = build_package(path, tmp_path / "plugin.zip")
    report = await smoke_package(Path(package.path))
    assert not report.ok
    assert any("synthetic startup failure" in error for error in report.errors)


async def test_smoke_rejects_unsafe_zip_without_importing(tmp_path: Path) -> None:
    package = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(package, "w") as bundle:
        bundle.writestr("../escaped.txt", "bad")
    report = await smoke_package(package)
    assert not report.ok
    assert "install" not in report.checks
    assert not (tmp_path / "escaped.txt").exists()


async def test_smoke_cancellation_cleans_the_installed_generation(tmp_path: Path) -> None:
    stopped = tmp_path / "stopped.txt"
    started = tmp_path / "started.txt"
    path = make_project(
        tmp_path,
        body=(
            "\nimport asyncio\nfrom pathlib import Path\n"
            "class Resource:\n"
            "    def unsubscribe(self):\n"
            f"        Path({str(stopped)!r}).write_text('stopped')\n"
            "@plugin.on_load\nasync def load(ctx):\n"
            "    ctx.record_subscription(Resource())\n"
            "@plugin.on_startup\nasync def start(ctx):\n"
            f"    Path({str(started)!r}).write_text('started')\n"
            "    await asyncio.Event().wait()\n"
        ),
    )
    package = build_package(path, tmp_path / "plugin.zip")
    task = asyncio.create_task(smoke_package(Path(package.path), timeout=10))
    try:
        async with asyncio.timeout(5):
            while not started.exists():
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_file()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_smoke_startup_timeout_is_a_failed_report(tmp_path: Path) -> None:
    path = make_project(
        tmp_path,
        body="\nimport asyncio\n@plugin.on_startup\nasync def start(ctx):\n    await asyncio.Event().wait()\n",
    )
    package = build_package(path, tmp_path / "plugin.zip")
    report = await smoke_package(Path(package.path), timeout=0.05)
    assert not report.ok
    assert any("超时" in error for error in report.errors)


async def test_smoke_reports_unsupported_reload_and_unverified_services(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    manifest = path / "plugin.toml"
    manifest.write_text("hot_reload = false\n" + manifest.read_text(encoding="utf-8"), encoding="utf-8")
    package = build_package(path, tmp_path / "plugin.zip")
    report = await smoke_package(Path(package.path))
    assert report.ok, report.errors
    assert "reload" in report.not_applicable
    assert "reload" not in report.checks
    assert "real_services" in report.unverified
    assert "database_migration" in report.unverified


async def test_smoke_reports_digest_of_the_bytes_actually_installed(tmp_path: Path, monkeypatch) -> None:
    first = build_package(make_project(tmp_path, "first"), tmp_path / "first.zip")
    second = build_package(make_project(tmp_path, "second"), tmp_path / "second.zip")
    second_bytes = Path(second.path).read_bytes()
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        return second_bytes if path == Path(first.path) else original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    report = await smoke_package(Path(first.path))
    assert report.ok, report.errors
    assert report.sha256 == hashlib.sha256(second_bytes).hexdigest()


async def test_smoke_final_cleanup_failure_is_not_reported_as_success(tmp_path: Path) -> None:
    counter = tmp_path / "stops.txt"
    path = make_project(
        tmp_path,
        body=(
            "\nfrom pathlib import Path\n"
            "@plugin.on_shutdown\nasync def stop(ctx):\n"
            f"    counter = Path({str(counter)!r})\n"
            "    count = int(counter.read_text()) if counter.exists() else 0\n"
            "    counter.write_text(str(count + 1))\n"
            "    if count >= 2:\n"
            "        raise RuntimeError('synthetic final cleanup failure')\n"
        ),
    )
    package = build_package(path, tmp_path / "plugin.zip")
    report = await smoke_package(Path(package.path))
    assert not report.ok
    assert any("synthetic final cleanup failure" in error for error in report.errors)
