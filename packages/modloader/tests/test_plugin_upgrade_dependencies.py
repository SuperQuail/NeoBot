"""维护升级按真实前置闭包验收，预检错误不得切换数据。"""

import pytest

from neobot_modloader.sdk.tooling import export_contract
from neobot_modloader.sdk.tooling.upgrade import upgrade_package
from plugin_upgrade_helpers import package, project
from test_plugin_upgrade import _installed, _rows


def _requires(source, dependency="foundation>=1.0"):
    manifest = source / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("[sdk]", f'dependencies = ["{dependency}"]\n[sdk]', 1),
        encoding="utf-8",
    )
    result = export_contract(source)
    assert result.ok, result.errors


def _dependency(root, name="foundation", *, dependencies=(), enabled=True, marker=None):
    source = root / name
    source.mkdir(parents=True)
    (source / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "1.0"\nenabled = {str(enabled).lower()}\n', encoding="utf-8"
    )
    body = f'from neobot_modloader import Plugin\nplugin = Plugin("{name}", version="1.0", dependencies={dependencies!r})\n'
    if marker is not None:
        body += f'from pathlib import Path\n@plugin.on_startup\nasync def start(ctx):\n    with Path({str(marker)!r}).open("a", encoding="utf-8") as stream:\n        stream.write("{name}\\n")\n'
    (source / "__init__.py").write_text(body, encoding="utf-8")
    return source


@pytest.mark.parametrize("official", [False, True])
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_upgrade_and_rollback_start_only_required_dependency_closure(tmp_path, official, startup_failure):
    plugins, data = _installed(tmp_path)
    _requires(plugins / "tasks")
    marker = tmp_path / "started.txt"
    _dependency(plugins, "leaf", marker=marker)
    builtin = tmp_path / "builtin"
    _dependency(builtin if official else plugins, dependencies=("leaf",), marker=marker)
    unrelated = _dependency(plugins, "unrelated")
    imported = tmp_path / "unrelated-imported"
    (unrelated / "__init__.py").write_text(
        f'from pathlib import Path\nPath({str(imported)!r}).touch()\nraise RuntimeError("无关插件不能导入")\n',
        encoding="utf-8",
    )
    if official:
        shadow = _dependency(plugins, "foundation")
        (shadow / "__init__.py").write_text('raise RuntimeError("第三方副本不能接管官方身份")\n', encoding="utf-8")
    source = project(tmp_path / "new-source", 2, startup_failure=startup_failure)
    _requires(source)
    candidate = package(source, tmp_path / "new.zip")
    report = await upgrade_package(
        candidate, plugin_dir=plugins, data_dir=data, name="tasks", builtin_plugin_dirs=(builtin,) if official else ()
    )
    assert report.ok is not startup_failure, report.errors
    assert report.restored is startup_failure, report.errors
    assert _rows(data, "text" if startup_failure else "title") == [(1, "历史待办")]
    assert marker.read_text(encoding="utf-8").splitlines() == ["leaf", "foundation"] * (2 if startup_failure else 1)
    assert not imported.exists()


@pytest.mark.parametrize("failure", ["missing", "version", "disabled", "cycle"])
async def test_dependency_preflight_failure_keeps_old_code_and_data(tmp_path, failure):
    plugins, data = _installed(tmp_path)
    source = project(tmp_path / "new-source", 2)
    _requires(source, "foundation>=2.0" if failure == "version" else "foundation")
    if failure != "missing":
        _dependency(plugins, dependencies=("tasks",) if failure == "cycle" else (), enabled=failure != "disabled")
    before = (plugins / "tasks/__init__.py").read_bytes()
    candidate = package(source, tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert "switch" not in report.checks
    assert (plugins / "tasks/__init__.py").read_bytes() == before
    assert _rows(data, "text") == [(1, "历史待办")]
