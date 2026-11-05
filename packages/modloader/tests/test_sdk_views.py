"""包内页面的范围由声明控制，不能读取代码或跨目录资源。"""

from types import SimpleNamespace

import pytest

from neobot_modloader import ActionError


def runtime_fixture(tmp_path, monkeypatch):
    from neobot_modloader.sdk import views

    root = tmp_path / "plugin"
    assets = root / "web" / "subscriptions"
    assets.mkdir(parents=True)
    (assets / "index.html").write_text("<h1>订阅</h1>", encoding="utf-8")
    (assets / "app.js").write_text("window.ready = true", encoding="utf-8")
    (root / "private.py").write_text("private = True", encoding="utf-8")
    (assets / "config.toml").write_text("value = 1", encoding="utf-8")
    (root / "plugin.toml").write_text(
        'name="demo"\nversion="1.0.0"\n[sdk]\nversion=1\npages=["web/subscriptions/index.html"]\n',
        encoding="utf-8",
    )
    contract = {
        "views": [
            {"id": "subscriptions", "title": "直播订阅", "entry": "web/subscriptions/index.html", "anchors": ["group"]}
        ]
    }
    monkeypatch.setattr(views, "describe_runtime_surface", lambda runtime, name: {"contract": contract})
    control = SimpleNamespace(get=lambda name: SimpleNamespace(path=root) if name == "demo" else None)
    return SimpleNamespace(control=control, _loaded_modules={}), assets


def test_declared_page_and_asset_are_resolved(tmp_path, monkeypatch):
    from neobot_modloader.sdk.views import describe_runtime_views, resolve_runtime_view_asset

    runtime, assets = runtime_fixture(tmp_path, monkeypatch)
    assert describe_runtime_views(runtime, "demo")[0]["id"] == "subscriptions"
    assert resolve_runtime_view_asset(runtime, "demo", "subscriptions", "") == assets / "index.html"
    assert resolve_runtime_view_asset(runtime, "demo", "subscriptions", "app.js") == assets / "app.js"


@pytest.mark.parametrize(
    "relative", ["../../private.py", "/private.py", "C:/private.py", "config.toml", ".env", "sub/../app.js"]
)
def test_private_or_escaped_files_are_not_public(tmp_path, monkeypatch, relative):
    from neobot_modloader.sdk.views import resolve_runtime_view_asset

    runtime, _ = runtime_fixture(tmp_path, monkeypatch)
    with pytest.raises(ActionError) as error:
        resolve_runtime_view_asset(runtime, "demo", "subscriptions", relative)
    assert error.value.code == "view_asset_not_found"


def test_page_entry_must_be_in_the_manifest_distribution(tmp_path, monkeypatch):
    from neobot_modloader.sdk.views import describe_runtime_views

    runtime, assets = runtime_fixture(tmp_path, monkeypatch)
    (assets.parents[1] / "plugin.toml").write_text('name="demo"\n[sdk]\npages=[]\n', encoding="utf-8")
    with pytest.raises(ActionError) as error:
        describe_runtime_views(runtime, "demo")
    assert error.value.code == "contract_invalid"


def test_page_revision_changes_with_assets_or_plugin_generation(tmp_path, monkeypatch):
    from neobot_modloader.sdk.views import describe_runtime_views

    runtime, assets = runtime_fixture(tmp_path, monkeypatch)
    initial = describe_runtime_views(runtime, "demo")[0]["revision"]
    assert describe_runtime_views(runtime, "demo")[0]["revision"] == initial
    (assets / "app.js").write_text("window.example = true", encoding="utf-8")
    updated = describe_runtime_views(runtime, "demo")[0]["revision"]
    assert updated != initial
    runtime._loaded_modules["demo"] = ("demo_g2",)
    assert describe_runtime_views(runtime, "demo")[0]["revision"] != updated
