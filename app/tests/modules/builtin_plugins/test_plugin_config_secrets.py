"""插件配置文件在线编辑：密钥只写不读。

配置文件位于插件数据目录 plugins_data/<插件名>/config.toml（官方与第三方插件同一个位置）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neobot_app.builtin_plugins.dashboard.plugin_config import (
    PluginConfigEditor,
    PluginConfigError,
)
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER

PLUGIN_CONFIG = """api_key = "sk-plugin-secret"
base_url = "https://api.example.com"
timeout = 30

[extra]
token = "tok-plugin-secret"
"""


def _editor(tmp_path: Path, **kwargs) -> PluginConfigEditor:
    path = tmp_path / "plugins_data" / "demo" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLUGIN_CONFIG, encoding="utf-8")
    return PluginConfigEditor(path, **kwargs)


def test_read_masks_secrets_and_disables_source(tmp_path: Path) -> None:
    """读取时密钥替换为占位符，且不返回源码（避免绕过脱敏拿明文）。"""
    document = _editor(tmp_path).read()

    assert document["config"]["api_key"] == SECRET_PLACEHOLDER
    assert document["config"]["extra"]["token"] == SECRET_PLACEHOLDER
    assert document["config"]["base_url"] == "https://api.example.com"
    assert document["source"] == ""
    assert document["source_available"] is False
    assert document["secret_policy"] == "write_only"
    assert "sk-plugin-secret" not in json.dumps(document, ensure_ascii=False)
    assert "tok-plugin-secret" not in json.dumps(document, ensure_ascii=False)

    fields = {item["name"]: item for item in document["schema"]}
    assert fields["api_key"]["sensitive"] is True
    assert fields["api_key"]["has_value"] is True
    assert fields["api_key"]["value"] == ""
    assert fields["base_url"]["value"] == "https://api.example.com"


def test_save_keeps_secret_when_placeholder_or_blank(tmp_path: Path) -> None:
    """占位符/留空表示不修改，密钥原样保留。"""
    editor = _editor(tmp_path)

    editor.save(config={"api_key": SECRET_PLACEHOLDER, "base_url": "https://api.example.com/v2"})
    text = editor.path.read_text(encoding="utf-8")
    assert 'api_key = "sk-plugin-secret"' in text
    assert 'base_url = "https://api.example.com/v2"' in text

    editor.save(config={"api_key": "", "base_url": "https://api.example.com/v3"})
    assert 'api_key = "sk-plugin-secret"' in editor.path.read_text(encoding="utf-8")


def test_save_updates_secret_with_new_value(tmp_path: Path) -> None:
    """提交新值时覆盖旧密钥，之后依然读不到明文。"""
    editor = _editor(tmp_path)

    editor.save(config={"api_key": "sk-new-secret"})
    text = editor.path.read_text(encoding="utf-8")
    assert 'api_key = "sk-new-secret"' in text
    assert "sk-plugin-secret" not in text
    assert editor.read()["config"]["api_key"] == SECRET_PLACEHOLDER


def test_save_rejects_source_when_secrets_present(tmp_path: Path) -> None:
    """含密钥的插件配置禁止源码模式编辑。"""
    editor = _editor(tmp_path)

    with pytest.raises(PluginConfigError):
        editor.save(source='api_key = "sk-x"\n')


def test_missing_file_renders_defaults_and_creates_on_save(tmp_path: Path) -> None:
    """配置还没保存过时按插件默认值渲染，首次保存才创建文件。"""
    path = tmp_path / "plugins_data" / "demo" / "config.toml"
    editor = PluginConfigEditor(path, defaults={"host": "0.0.0.0", "port": 9981})

    document = editor.read()
    assert document["exists"] is False
    assert document["revision"] == ""
    assert document["config"] == {"host": "0.0.0.0", "port": 9981}

    saved = editor.save(config={"port": 9999})
    assert saved["exists"] is True
    assert path.read_text(encoding="utf-8").strip() == "port = 9999"
    # 未提交的字段继续沿用插件默认值
    assert saved["config"] == {"host": "0.0.0.0", "port": 9999}


def test_saving_empty_config_is_rejected(tmp_path: Path) -> None:
    """空配置没有意义，直接拒绝，避免写空文件把插件配置抹掉。"""
    editor = _editor(tmp_path)

    with pytest.raises(PluginConfigError):
        editor.save(config={})


@pytest.mark.parametrize("key", ["cookie", "session_cookie", "Cookie", "authorization", "access_key"])
def test_authentication_fields_never_leave_config_documents(tmp_path: Path, key: str) -> None:
    """认证字段的保护规则覆盖配置、默认值、嵌套描述和源码。"""
    secret = "synthetic-authentication-value"
    path = tmp_path / "config.toml"
    editor = PluginConfigEditor(path, defaults={key: secret, "interval": 60})

    document = editor.read()

    assert document["config"][key] == SECRET_PLACEHOLDER
    assert document["defaults"][key] == SECRET_PLACEHOLDER
    assert document["source"] == ""
    assert document["source_available"] is False
    assert secret not in json.dumps(document, ensure_ascii=False)
    field = next(item for item in document["schema"] if item["name"] == key)
    assert field["sensitive"] is True
    assert field["has_value"] is True
    assert field["value"] == ""


def test_cookie_keeps_and_replaces_saved_value_without_readback(tmp_path: Path) -> None:
    """Cookie 表单沿用其它密钥的保留与替换语义。"""
    path = tmp_path / "config.toml"
    path.write_text('cookie = "synthetic-cookie-before"\ninterval = 60\n', encoding="utf-8")
    editor = PluginConfigEditor(path)

    for retained in ("", SECRET_PLACEHOLDER):
        saved = editor.save(config={"cookie": retained, "interval": 30})
        assert 'cookie = "synthetic-cookie-before"' in path.read_text(encoding="utf-8")
        assert "synthetic-cookie-before" not in json.dumps(saved, ensure_ascii=False)

    saved = editor.save(config={"cookie": "synthetic-cookie-after"})
    assert 'cookie = "synthetic-cookie-after"' in path.read_text(encoding="utf-8")
    assert "synthetic-cookie-after" not in json.dumps(saved, ensure_ascii=False)


def test_cookie_default_also_protects_source_writes(tmp_path: Path) -> None:
    """尚未保存的打包默认值同样禁止通过源码模式绕过表单保护。"""
    editor = PluginConfigEditor(
        tmp_path / "config.toml", defaults={"cookie": "synthetic-default-cookie", "interval": 60}
    )

    with pytest.raises(PluginConfigError, match="禁用源码编辑"):
        editor.save(source="interval = 30\n")

    assert editor.exists is False
    saved = editor.save(config={"cookie": "", "interval": 30})
    assert saved["config"]["cookie"] == SECRET_PLACEHOLDER
    assert "synthetic-default-cookie" not in json.dumps(saved, ensure_ascii=False)


def test_cookie_is_masked_inside_tables_and_table_lists(tmp_path: Path) -> None:
    """分组描述和列表条目的聚合 value 不能保留嵌套 Cookie。"""
    editor = PluginConfigEditor(
        tmp_path / "config.toml",
        defaults={
            "service": {"cookie": "synthetic-table-cookie"},
            "accounts": [{"cookie": "synthetic-list-cookie", "name": "test"}],
        },
    )

    document = editor.read()
    serialized = json.dumps(document, ensure_ascii=False)

    assert "synthetic-table-cookie" not in serialized
    assert "synthetic-list-cookie" not in serialized
    assert document["source_available"] is False
