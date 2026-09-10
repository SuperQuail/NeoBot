"""第三方插件 plugin.toml 在线编辑：密钥只写不读。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neobot_app.builtin_plugins.dashboard.plugin_config import (
    PluginConfigEditor,
    PluginConfigError,
)
from neobot_app.builtin_plugins.dashboard.security import SECRET_PLACEHOLDER

PLUGIN_TOML = '''name = "demo"
version = "1.0.0"

[config]
api_key = "sk-plugin-secret"
base_url = "https://api.example.com"
timeout = 30

[config.extra]
token = "tok-plugin-secret"
'''


def _editor(tmp_path: Path) -> PluginConfigEditor:
    path = tmp_path / "plugin.toml"
    path.write_text(PLUGIN_TOML, encoding="utf-8")
    return PluginConfigEditor(path)


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

    editor.save(
        config={"api_key": SECRET_PLACEHOLDER, "base_url": "https://api.example.com/v2"}
    )
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
