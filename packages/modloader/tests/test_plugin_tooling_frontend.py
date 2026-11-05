"""前端声明在本地工具与 CI 之间使用同一套静态规则。"""

import json
from pathlib import Path

import pytest

from neobot_modloader.sdk.tooling import build_package, check_project
from neobot_modloader.sdk.tooling.frontend import read_frontend
from plugin_tooling_helpers import make_project


def frontend_project(root: Path) -> tuple[Path, dict]:
    path = make_project(root)
    frontend = path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@12.3.4", "scripts": {"verify": "test", "build": "build"}}),
        encoding="utf-8",
    )
    (frontend / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    metadata = {"sdk": {"version": 1, "frontend": {"path": "frontend"}, "pages": ["web/index.html"]}}
    return path, metadata


def test_python_plugin_does_not_require_frontend_tools(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    assert read_frontend(path, {"sdk": {"version": 1}}) is None
    assert check_project(path).ok


def test_declared_frontend_can_be_read_before_page_build(tmp_path: Path) -> None:
    path, metadata = frontend_project(tmp_path)
    assert not (path / "web" / "index.html").exists()
    assert read_frontend(path, metadata) == path / "frontend"


def test_conventional_frontend_project_requires_an_explicit_declaration(tmp_path: Path) -> None:
    path, _ = frontend_project(tmp_path)
    with pytest.raises(ValueError, match="sdk.frontend"):
        read_frontend(path, {"sdk": {"version": 1}})


@pytest.mark.parametrize("value", [False, [], "frontend", {}, {"path": "../outside"}, {"path": "/outside"}])
def test_frontend_declaration_rejects_invalid_type_and_path(tmp_path: Path, value: object) -> None:
    path, metadata = frontend_project(tmp_path)
    metadata["sdk"]["frontend"] = value
    with pytest.raises(ValueError):
        read_frontend(path, metadata)


@pytest.mark.parametrize("filename", ["package.json", "pnpm-lock.yaml"])
def test_frontend_requires_package_and_lock_files(tmp_path: Path, filename: str) -> None:
    path, metadata = frontend_project(tmp_path)
    (path / "frontend" / filename).unlink()
    with pytest.raises(ValueError, match=filename):
        read_frontend(path, metadata)


@pytest.mark.parametrize("manager", ["npm@11.0.0", "pnpm@latest", "pnpm@^12", "pnpm@12.3", "pnpm@12.3.4;echo bad"])
def test_frontend_requires_an_exact_pnpm_version(tmp_path: Path, manager: str) -> None:
    path, metadata = frontend_project(tmp_path)
    package = path / "frontend" / "package.json"
    value = json.loads(package.read_text(encoding="utf-8"))
    value["packageManager"] = manager
    package.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="packageManager"):
        read_frontend(path, metadata)


@pytest.mark.parametrize("scripts", [{}, {"verify": "check"}, {"verify": " ", "build": "build"}])
def test_frontend_requires_verify_and_build_commands(tmp_path: Path, scripts: dict) -> None:
    path, metadata = frontend_project(tmp_path)
    package = path / "frontend" / "package.json"
    package.write_text(json.dumps({"packageManager": "pnpm@12.3.4", "scripts": scripts}), encoding="utf-8")
    with pytest.raises(ValueError, match="scripts"):
        read_frontend(path, metadata)


def test_frontend_requires_page_declarations(tmp_path: Path) -> None:
    path, metadata = frontend_project(tmp_path)
    metadata["sdk"]["pages"] = []
    with pytest.raises(ValueError, match="sdk.pages"):
        read_frontend(path, metadata)


def test_static_check_checks_pages_only_after_frontend_declaration(tmp_path: Path) -> None:
    path, _ = frontend_project(tmp_path)
    manifest = path / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + 'pages = ["web/index.html"]\n[sdk.frontend]\npath = "frontend"\n',
        encoding="utf-8",
    )
    report = check_project(path)
    assert not report.ok
    assert any("sdk.pages[0]" in error for error in report.errors)
    (path / "web").mkdir()
    (path / "web" / "index.html").write_text("<p>synthetic page</p>", encoding="utf-8")
    assert check_project(path).ok


@pytest.mark.parametrize("directory", ["dist", "ui/dist"])
def test_package_contains_declared_dist_page_and_built_assets(tmp_path: Path, directory: str) -> None:
    import zipfile

    path = make_project(tmp_path)
    manifest = path / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + f'pages = ["{directory}/index.html"]\n', encoding="utf-8"
    )
    built = path / directory
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text('<script src="./assets/app.js"></script>', encoding="utf-8")
    (built / "assets" / "app.js").write_text("console.log('synthetic asset')", encoding="utf-8")
    unused = path / "unrelated" / "dist"
    unused.mkdir(parents=True)
    (unused / "old.txt").write_text("not distributed", encoding="utf-8")
    report = build_package(path, tmp_path / "plugin.zip")
    assert report.ok, report.errors
    with zipfile.ZipFile(report.path) as bundle:
        assert bundle.read(f"sample/{directory}/index.html") == (built / "index.html").read_bytes()
        assert bundle.read(f"sample/{directory}/assets/app.js") == (built / "assets" / "app.js").read_bytes()
        assert "sample/unrelated/dist/old.txt" not in bundle.namelist()
