"""面板保存 config.toml 时，必须保留表单不认识的键。

面板表单的字段来自 ``BotConfig`` 的声明，文件里允许存在声明之外的键：
用户自定义分区、插件写进去的字段、更新版本留下的新字段。旧实现把这些键
当成「表单里删掉的键」，``_diff_document`` 直接给出删除指令，一次面板保存
就会把它们从 config.toml 里抹掉。
"""

from __future__ import annotations

from pathlib import Path

from neobot_app.builtin_plugins.dashboard.config_manager import BotConfigManager


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
