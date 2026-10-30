"""独立模板仓库初始化后必须得到能实际执行的插件工程。"""

import json
from pathlib import Path

from neobot_modloader.sdk.tooling import check_project, init_project


def _template(root: Path) -> Path:
    recipe = root / "template"
    recipe.mkdir(parents=True)
    (root / "template.json").write_text(json.dumps({"schema_version": 2, "template": "template"}))
    (recipe / "plugin.toml").write_text(
        'name = "__PLUGIN_NAME__"\nversion = "0.1.0"\n[sdk]\nversion = 1\ncontract = "plugin.contract.json"\n'
    )
    (recipe / "__init__.py").write_text('from neobot_modloader import Plugin\nplugin = Plugin("__PLUGIN_NAME__")\n')
    return root


def test_external_template_is_instantiated_without_editing_its_source(tmp_path):
    template = _template(tmp_path / "template")
    destination = tmp_path / "created"
    report = init_project(destination, "my_plugin", template=template)
    assert report.ok, report.errors
    assert check_project(destination).ok
    assert 'Plugin("my_plugin")' in (destination / "__init__.py").read_text()
    assert "__PLUGIN_NAME__" in (template / "template/__init__.py").read_text()
    assert not (destination / "template.json").exists()


def test_external_template_multiple_variants_are_a_reported_failure(tmp_path):
    template = _template(tmp_path / "template")
    (template / "template.json").write_text(
        json.dumps({"schema_version": 2, "template": "template", "variants": {"other": "template"}})
    )
    report = init_project(tmp_path / "created", "my_plugin", template=template)
    assert not report.ok
    assert any("variants" in error for error in report.errors)
    assert not (tmp_path / "created").exists()


def test_external_template_cannot_reference_a_recipe_outside_repository(tmp_path):
    template = _template(tmp_path / "template")
    manifest = {"schema_version": 2, "template": "../outside"}
    (template / "template.json").write_text(json.dumps(manifest))
    report = init_project(tmp_path / "created", "my_plugin", template=template)
    assert not report.ok
    assert any("路径" in error for error in report.errors)


def test_external_template_must_declare_one_existing_project_directory(tmp_path):
    template = _template(tmp_path / "template")
    (template / "template.json").write_text(json.dumps({"schema_version": 2, "template": "missing"}))
    report = init_project(tmp_path / "created", "my_plugin", template=template)
    assert not report.ok
    assert any("目录不存在" in error for error in report.errors)
    assert not (tmp_path / "created").exists()


def test_init_help_does_not_ask_authors_to_select_a_variant(capsys):
    import pytest

    from neobot_modloader.sdk.tooling.cli import main

    with pytest.raises(SystemExit) as caught:
        main(["init", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--template" in help_text
    assert "--variant" not in help_text


def test_init_can_complete_while_verified_source_has_an_open_reader(tmp_path, monkeypatch):
    from neobot_modloader.sdk.tooling import project

    export = project.export_contract
    readers = []

    def export_with_reader(path):
        report = export(path)
        # Windows 默认读句柄不共享 DELETE，模拟编辑器或扫描器正在读取已验证入口。
        readers.append((path / "__init__.py").open("rb"))
        return report

    monkeypatch.setattr(project, "export_contract", export_with_reader)
    try:
        report = init_project(tmp_path / "created", "reader_example")
        assert report.ok, report.errors
        assert check_project(tmp_path / "created").ok
    finally:
        for reader in readers:
            reader.close()
