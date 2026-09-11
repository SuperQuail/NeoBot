"""插件配置的字段说明（注释）与注释保留。

覆盖三条链路：
1. plugin.toml 的 [config] 注释被面板读成字段说明（第三方纯 TOML 插件也有说明）；
2. 首次生成的 plugins_data/<name>/config.toml 自带注释（文件自解释）；
3. 保存后注释不被冲掉，且用户自己写的注释优先。
另外守住官方插件的 plugin.toml 默认值与 pydantic 模型默认值一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.plugin_config import (
    PluginConfigEditor,
    apply_field_descriptions,
    read_manifest_comments,
)
from neobot_app.builtin_plugins.starship.config import StarshipConfig

OFFICIAL_DIR = Path(__file__).resolve().parents[2] / "src" / "neobot_app" / "builtin_plugins"

MANIFEST = """name = "demo"
version = "1.0.0"

# 这是表头说明
[config]
# 监听端口
# （被占用时向后顺延）
port = 8080
# 是否开启调试
debug = false
city = "Shanghai"
"""


def write_manifest(tmp_path: Path, text: str = MANIFEST) -> Path:
    path = tmp_path / "plugin.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. 读取 plugin.toml 注释
# ---------------------------------------------------------------------------


def test_read_manifest_comments_extracts_keys_and_table_hint(tmp_path: Path) -> None:
    comments = read_manifest_comments(write_manifest(tmp_path))
    assert comments["port"] == "监听端口 （被占用时向后顺延）"
    assert comments["debug"] == "是否开启调试"
    assert comments[""] == "这是表头说明"
    assert "city" not in comments


def test_read_manifest_comments_tolerates_missing_or_broken_file(tmp_path: Path) -> None:
    assert read_manifest_comments(None) == {}
    assert read_manifest_comments(tmp_path / "nope.toml") == {}
    broken = tmp_path / "broken.toml"
    broken.write_text("[config\nport = ", encoding="utf-8")
    assert read_manifest_comments(broken) == {}
    plain = tmp_path / "plain.toml"
    plain.write_text('name = "x"\n', encoding="utf-8")
    assert read_manifest_comments(plain) == {}


def test_apply_field_descriptions_keeps_existing_text() -> None:
    schema = [
        {"name": "port", "kind": "scalar", "description": "模型自带的说明"},
        {"name": "debug", "kind": "scalar", "description": ""},
        {"name": "nested", "kind": "group", "fields": [{"name": "port", "kind": "scalar", "description": ""}]},
    ]
    apply_field_descriptions(schema, {"port": "注释说明", "debug": "开关注释", "nested.port": "嵌套注释"})
    assert schema[0]["description"] == "模型自带的说明"
    assert schema[1]["description"] == "开关注释"
    assert schema[2]["fields"][0]["description"] == "嵌套注释"


# ---------------------------------------------------------------------------
# 2/3. 生成与保存时的注释
# ---------------------------------------------------------------------------


def test_generated_config_file_carries_comments(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    editor = PluginConfigEditor(
        tmp_path / "config.toml",
        defaults={"port": 8080, "debug": False, "city": "Shanghai"},
        comments=read_manifest_comments(manifest),
    )
    document = editor.read()
    assert document["exists"] is False
    # 文件还没生成，但 TOML 源码已经带注释（前端 TOML 页与首次保存都基于它）
    assert "# 监听端口" in document["source"]
    assert "# 是否开启调试" in document["source"]
    # schema 里也有说明
    by_name = {item["name"]: item for item in document["schema"]}
    assert by_name["port"]["description"].startswith("监听端口")
    assert by_name["debug"]["description"] == "是否开启调试"
    # 没有单独注释的键用表头说明兜底
    assert by_name["city"]["description"] == "这是表头说明"

    saved = editor.save(config={**document["config"], "debug": True}, expected_revision=document["revision"])
    assert saved["exists"] is True
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "# 监听端口" in text
    assert "debug = true" in text
    assert saved["config"]["port"] == 8080


def test_save_preserves_user_comments_and_order(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# 用户自己写的端口说明\nport = 9000\n# 保留顺序\ndebug = false\n",
        encoding="utf-8",
    )
    editor = PluginConfigEditor(
        config_path,
        defaults={"port": 8080, "debug": False},
        comments={"port": "插件作者写的说明"},
    )
    document = editor.read()
    by_name = {item["name"]: item for item in document["schema"]}
    # 文件里的注释优先于 plugin.toml 的注释
    assert by_name["port"]["description"] == "用户自己写的端口说明"

    editor.save(config={**document["config"], "port": 9100})
    text = config_path.read_text(encoding="utf-8")
    assert "# 用户自己写的端口说明" in text
    assert "port = 9100" in text
    parsed = tomlkit.parse(text)
    assert list(parsed.keys()) == ["port", "debug"]


def test_save_adds_comment_for_new_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    editor = PluginConfigEditor(
        config_path,
        defaults={"port": 8080},
        comments={"port": "端口说明", "extra": "新增项说明"},
    )
    editor.save(config={"port": 8080, "extra": 1})
    text = config_path.read_text(encoding="utf-8")
    assert "# 端口说明" in text
    assert "# 新增项说明" in text


# ---------------------------------------------------------------------------
# 官方插件：注释齐全 + 默认值与模型一致
# ---------------------------------------------------------------------------


def load_manifest_config(plugin: str) -> dict:
    manifest = OFFICIAL_DIR / plugin / "plugin.toml"
    return dict(tomlkit.parse(manifest.read_text(encoding="utf-8")).get("config") or {})


@pytest.mark.parametrize(
    ("plugin", "model"),
    [("dashboard", DashboardConfig), ("starship", StarshipConfig)],
)
def test_official_plugin_config_is_documented(plugin: str, model: type) -> None:
    comments = read_manifest_comments(OFFICIAL_DIR / plugin / "plugin.toml")
    fields = set(model.model_fields)
    for name in fields:
        assert comments.get(name), f"{plugin} 的字段 {name} 缺少 plugin.toml 注释"
        assert model.model_fields[name].description, f"{plugin} 的字段 {name} 缺少模型 description"
    # plugin.toml 的 [config] 只应包含模型认识的键
    assert set(load_manifest_config(plugin)) <= fields


@pytest.mark.parametrize(
    ("plugin", "model"),
    [("dashboard", DashboardConfig), ("starship", StarshipConfig)],
)
def test_official_plugin_packaged_defaults_match_model(plugin: str, model: type) -> None:
    packaged = load_manifest_config(plugin)
    for name, value in packaged.items():
        assert model.model_fields[name].default == value, (
            f"{plugin}.{name} 的 plugin.toml 默认值与模型默认值不一致"
        )
