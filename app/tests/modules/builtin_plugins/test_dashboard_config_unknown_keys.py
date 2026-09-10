"""面板保存 config.toml 时，必须保留表单不认识的键。

面板表单的字段来自 ``BotConfig`` 的声明，文件里允许存在声明之外的键：
用户自定义分区、插件写进去的字段、更新版本留下的新字段。旧实现把这些键
当成「表单里删掉的键」，``_diff_document`` 直接给出删除指令，一次面板保存
就会把它们从 config.toml 里抹掉。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_app.builtin_plugins.dashboard.config_manager import (
    BotConfigManager,
    ConfigValidationError,
)


def _manager(tmp_path: Path) -> tuple[BotConfigManager, Path]:
    config_path = tmp_path / "config.toml"
    return (
        BotConfigManager(config_path=config_path, backup_dir=tmp_path / "backup"),
        config_path,
    )


def test_form_save_keeps_unknown_sections(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n'
        'my_top_level = "keep-me"\n'
        "\n[bot]\n"
        'nick_name = "Neo"\n'
        "custom_in_section = 7\n"
        "\n[my_plugin]\n"
        "enabled = true\n",
        encoding="utf-8",
    )

    document = manager.read()
    manager.save(config=document["config"])

    saved = config_path.read_text(encoding="utf-8")
    assert "my_top_level" in saved
    assert "[my_plugin]" in saved
    assert "custom_in_section = 7" in saved


def test_form_save_still_deletes_known_fields(tmp_path: Path) -> None:
    """托管字段的删除必须照旧生效，不能被「未知键保护」误伤。"""
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n\n[bot]\nnick_name = "Neo"\nalias_name = ["N"]\n',
        encoding="utf-8",
    )

    document = manager.read()
    payload = {
        key: value
        for key, value in document["config"].items()
        if key not in {"willing"}
    }
    manager.save(config=payload)

    saved = config_path.read_text(encoding="utf-8")
    assert "[willing]" not in saved


def test_form_save_still_deletes_free_mapping_keys(tmp_path: Path) -> None:
    """分群系数这类自由映射：键由用户决定，表单删掉就该删掉。"""
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n'
        "\n[chat.group_response_coefficient]\n"
        '999001 = 0.5\n'
        '999002 = 0.8\n',
        encoding="utf-8",
    )

    document = manager.read()
    chat = dict(document["config"]["chat"])
    chat["group_response_coefficient"] = {"999001": 0.5}
    manager.save(config={**document["config"], "chat": chat})

    saved = config_path.read_text(encoding="utf-8")
    assert "999002" not in saved
    assert "999001 = 0.5" in saved


def test_section_save_survives_extra_keys(tmp_path: Path) -> None:
    """配置文件里已有面板不认识的键时，分区保存不能被「未知配置项」拦死。"""
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n'
        'my_top_level = "keep-me"\n'
        "\n[my_plugin]\n"
        "enabled = true\n"
        "\n[dashboard]\n"
        "port = 9981\n",
        encoding="utf-8",
    )

    manager.update_section("dashboard", {"port": 9999})

    saved = config_path.read_text(encoding="utf-8")
    assert "port = 9999" in saved
    assert "my_top_level" in saved
    assert "[my_plugin]" in saved


def test_section_save_rejects_unknown_key_in_edited_section(tmp_path: Path) -> None:
    """正在编辑的分区里出现未知键，依然要报错（不能静默写进去）。"""
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n\n[dashboard]\nport = 9981\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError):
        manager.update_section("dashboard", {"nope": 1})

    assert "nope" not in config_path.read_text(encoding="utf-8")


def test_plugins_proxy_save_survives_extra_keys(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n'
        "\n[my_plugin]\n"
        "enabled = true\n"
        "\n[plugins]\n"
        'proxy_mode = "system"\n',
        encoding="utf-8",
    )

    manager.update_plugins_proxy(mode="system", host="127.0.0.1", port=7890)

    saved = config_path.read_text(encoding="utf-8")
    assert "proxy_port = 7890" in saved
    assert "[my_plugin]" in saved
