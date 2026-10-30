"""页面静态验收复用宿主资源边界，按引用文件位置解析字面路径。"""

from neobot_modloader.sdk.tooling import check_project
from plugin_tooling_helpers import make_project, write_contract


def _page(tmp_path, html):
    source = make_project(tmp_path)
    manifest = source / "plugin.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + 'pages = ["web/index.html"]\n', encoding="utf-8")
    write_contract(source, "sample", views=[{"id": "home", "title": "页面", "entry": "web/index.html", "anchors": []}])
    (source / "web").mkdir()
    (source / "web/index.html").write_text(html, encoding="utf-8")
    return source


def test_missing_literal_resource_reports_the_referencing_file_and_path(tmp_path):
    source = _page(tmp_path, '<link rel="stylesheet" href="assets/missing.css?v=1#theme">')
    report = check_project(source)
    assert not report.ok
    assert "web/index.html" in report.errors[0] and "assets/missing.css" in report.errors[0]


def test_relative_css_and_js_resources_support_queries_fragments_and_url_escaping(tmp_path):
    source = _page(
        tmp_path,
        '<script src="_sdk.js"></script><link href="assets/main.css?v=1#theme"><script type="module" src="assets/main.js"></script>',
    )
    assets = source / "web/assets"
    assets.mkdir()
    (assets / "main.css").write_text('body { background: url("../images/a%20b.svg?v=1#icon"); }', encoding="utf-8")
    (assets / "main.js").write_text(
        'import "./part.js?version=1#module"; const path = "./not-a-reference.js";', encoding="utf-8"
    )
    (assets / "part.js").write_text("export const value = 1;", encoding="utf-8")
    (source / "web/images").mkdir()
    (source / "web/images/a b.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    report = check_project(source)
    assert report.ok, report.errors


def test_view_cannot_reference_python_even_when_packaged(tmp_path):
    source = _page(tmp_path, '<script src="module.py"></script>')
    (source / "web/module.py").write_text('value = "secret"', encoding="utf-8")
    report = check_project(source)
    assert not report.ok
    assert "module.py" in report.errors[0]


def test_host_stylesheet_does_not_need_to_be_copied_into_plugin_package(tmp_path):
    source = _page(tmp_path, '<link rel="stylesheet" href="_ui.css"><script src="_sdk.js"></script>')
    report = check_project(source)
    assert report.ok, report.errors


def test_nested_stylesheet_with_reserved_name_still_needs_a_local_file(tmp_path):
    source = _page(tmp_path, '<link rel="stylesheet" href="assets/_ui.css">')
    report = check_project(source)
    assert not report.ok
    assert "assets/_ui.css" in report.errors[0]


def test_encoded_parent_escape_is_not_treated_as_a_host_asset(tmp_path):
    source = _page(tmp_path, '<script src="%2e%2e/__init__.py"></script>')
    report = check_project(source)
    assert not report.ok
    assert "__init__.py" in report.errors[0]


def test_network_data_fragment_and_dynamic_expressions_are_not_guessed(tmp_path):
    source = _page(
        tmp_path,
        '<script src="https://example.invalid/bundle.js"></script><img src="data:image/png;base64,a"><a href="#local">本页</a><script>import(path);</script>',
    )
    report = check_project(source)
    assert report.ok, report.errors


def test_minified_module_literal_still_requires_its_distributed_file(tmp_path):
    source = _page(tmp_path, '<script type="module" src="app.js"></script>')
    (source / "web/app.js").write_text('import"./missing.js";', encoding="utf-8")
    report = check_project(source)
    assert not report.ok
    assert "missing.js" in report.errors[0]
