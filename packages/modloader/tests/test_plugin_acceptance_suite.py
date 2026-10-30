"""显式离线 suite 与既有联网测试互不混淆，所选用例仍必须完整执行。"""

from scripts.plugin_ci_support import read_spec
from neobot_modloader.sdk.tooling import check_project, init_project


def test_declared_acceptance_suite_is_shared_by_runner_and_static_check(tmp_path):
    source = tmp_path / "example"
    assert init_project(source, "example").ok
    acceptance = source / "tests/acceptance"
    acceptance.mkdir()
    (acceptance / "test_business.py").write_text("def test_business():\n    assert True\n")
    with (source / "plugin.toml").open("a") as handle:
        handle.write('\n[sdk.tests]\npath = "tests/acceptance"\n')
    assert check_project(source).ok
    assert read_spec(source).tests == acceptance


def test_declared_suite_cannot_escape_plugin_or_silently_disappear(tmp_path):
    source = tmp_path / "example"
    assert init_project(source, "example").ok
    with (source / "plugin.toml").open("a") as handle:
        handle.write('\n[sdk.tests]\npath = "../outside"\n')
    report = check_project(source)
    assert not report.ok
    assert any("路径" in error for error in report.errors)
