"""确定性包的内容、路径与体积边界。"""

import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from neobot_modloader.sdk.tooling import build_package, check_project
from plugin_tooling_helpers import make_project


def test_build_is_deterministic_and_excludes_development_files(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    for directory in (".git", ".venv", "node_modules", "__pycache__", "dist"):
        target = path / directory / "ignored.txt"
        target.parent.mkdir()
        target.write_text("development only", encoding="utf-8")
    first = build_package(path, tmp_path / "first.zip")
    os.utime(path / "__init__.py", (1000000000, 1000000000))
    second = build_package(path, tmp_path / "second.zip")
    assert first.ok, first.errors
    assert second.ok, second.errors
    assert first.sha256 == second.sha256
    with zipfile.ZipFile(first.path) as bundle:
        names = bundle.namelist()
        assert "sample/__init__.py" in names
        assert "sample/plugin.contract.json" in names
        assert not any("ignored.txt" in name for name in names)


@pytest.mark.parametrize("name", [".env", "credentials.json", "private.key", "config.toml"])
def test_sensitive_user_files_prevent_packaging(tmp_path: Path, name: str) -> None:
    path = make_project(tmp_path)
    (path / name).write_text("synthetic private data", encoding="utf-8")
    output = tmp_path / "plugin.zip"
    report = build_package(path, output)
    assert not report.ok
    assert not output.exists()
    assert any(name in error for error in report.errors)


def test_symlink_is_rejected_before_check_or_build(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (path / "linked.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"当前系统不允许创建 symlink: {exc}")
    assert not check_project(path).ok
    assert not build_package(path, tmp_path / "plugin.zip").ok


def test_invalid_contract_cannot_be_packaged(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    (path / "plugin.contract.json").write_text("not json", encoding="utf-8")
    assert not build_package(path, tmp_path / "plugin.zip").ok


def test_build_excludes_its_own_previous_output(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    output = path / "plugin.zip"
    first = build_package(path, output)
    second = build_package(path, output)
    assert first.ok and second.ok
    assert first.sha256 == second.sha256
    with zipfile.ZipFile(output) as bundle:
        assert not any(name.endswith("plugin.zip") for name in bundle.namelist())


def test_package_limits_preserve_previous_output(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    output = tmp_path / "plugin.zip"
    output.write_bytes(b"previous package")
    with patch("neobot_modloader.sdk.tooling.files.MAX_EXTRACTED_BYTES", 10):
        report = build_package(path, output)
    assert not report.ok
    assert output.read_bytes() == b"previous package"


def test_previous_output_does_not_count_toward_the_source_limit(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    output = path / "plugin.zip"
    output.write_bytes(b"previous package" * 1024)
    source_size = sum(item.stat().st_size for item in path.iterdir() if item != output)
    with patch("neobot_modloader.sdk.tooling.files.MAX_EXTRACTED_BYTES", source_size):
        report = build_package(path, output)
    assert report.ok, report.errors


def test_build_output_cannot_overwrite_the_plugin_entry(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    entry = path / "__init__.py"
    before = entry.read_bytes()
    report = build_package(path, entry)
    assert not report.ok
    assert entry.read_bytes() == before
