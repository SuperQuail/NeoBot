"""本体 config.toml 里的历史插件配置分区迁移测试。

官方插件（dashboard）的配置过去写在本体 config.toml 的同名分区里，
现在统一放在插件数据目录 plugins_data/<插件名>/config.toml，
是否启用则是 plugin_state.json 里的独立记录。
"""

from __future__ import annotations

import json
from pathlib import Path

import tomlkit

from neobot_app.config.plugin_config_migration import (
    migrate_legacy_plugin_config,
    plugin_config_file,
)


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "config_path": tmp_path / "config.toml",
        "data_dir": tmp_path / "plugins_data",
        "backup_dir": tmp_path / "config_backup",
        "state_file": tmp_path / "plugin_state.json",
    }


def _write_config(path: Path, body: str) -> None:
    path.write_text('version = "0.6.0"\n' + body, encoding="utf-8")


def _read_toml(path: Path) -> dict:
    return dict(tomlkit.parse(path.read_text(encoding="utf-8")).unwrap())


def test_moves_dashboard_section_into_plugin_data(tmp_path: Path) -> None:
    """[dashboard] 的值搬进插件数据目录，本体配置里不再保留该分区。"""
    paths = _paths(tmp_path)
    _write_config(
        paths["config_path"],
        '[debug]\nenabled = true\n\n'
        '[dashboard]\nenabled = true\nhost = "127.0.0.1"\nport = 9000\n'
        'session_timeout_minutes = 60\n',
    )

    migrated = migrate_legacy_plugin_config(**paths)

    assert migrated == ["dashboard"]
    target = plugin_config_file("dashboard", data_dir=paths["data_dir"])
    assert _read_toml(target) == {
        "host": "127.0.0.1",
        "port": 9000,
        "session_timeout_minutes": 60,
    }
    raw = paths["config_path"].read_text(encoding="utf-8")
    assert "[dashboard]" not in raw
    assert "[debug]" in raw
    # 改动前有备份
    assert list(paths["backup_dir"].glob("config_*.toml"))


def test_disabled_dashboard_becomes_state_record(tmp_path: Path) -> None:
    """enabled = false 转成插件停用记录，不再作为配置项保存。"""
    paths = _paths(tmp_path)
    _write_config(
        paths["config_path"],
        '[dashboard]\nenabled = false\nhost = "0.0.0.0"\nport = 9981\n',
    )

    migrated = migrate_legacy_plugin_config(**paths)

    assert migrated == ["dashboard"]
    state = json.loads(paths["state_file"].read_text(encoding="utf-8"))
    assert state["plugins"]["dashboard"]["enabled"] is False
    target = plugin_config_file("dashboard", data_dir=paths["data_dir"])
    assert "enabled" not in _read_toml(target)


def test_enabled_true_writes_no_state_record(tmp_path: Path) -> None:
    """默认启用不写记录：只有显式停用过才留下独立记录。"""
    paths = _paths(tmp_path)
    _write_config(paths["config_path"], '[dashboard]\nenabled = true\nport = 9981\n')

    assert migrate_legacy_plugin_config(**paths) == ["dashboard"]

    assert not paths["state_file"].exists()


def test_legacy_console_section_is_carried(tmp_path: Path) -> None:
    """更早版本的 [console] 只带走面板认识的字段，控制台专用字段丢弃。"""
    paths = _paths(tmp_path)
    _write_config(
        paths["config_path"],
        '[console]\nenabled = true\nhost = "127.0.0.1"\nport = 9000\n'
        'admin_enabled = false\nadmin_port = 9891\nport_search_limit = 50\n',
    )

    migrated = migrate_legacy_plugin_config(**paths)

    assert migrated == ["dashboard"]
    target = plugin_config_file("dashboard", data_dir=paths["data_dir"])
    assert _read_toml(target) == {"host": "127.0.0.1", "port": 9000}
    assert "[console]" not in paths["config_path"].read_text(encoding="utf-8")


def test_existing_plugin_config_wins(tmp_path: Path) -> None:
    """插件数据目录里已有配置时不覆盖用户改过的值，只清理历史分区。"""
    paths = _paths(tmp_path)
    target = plugin_config_file("dashboard", data_dir=paths["data_dir"])
    target.parent.mkdir(parents=True)
    target.write_text('port = 9999\n', encoding="utf-8")
    _write_config(paths["config_path"], '[dashboard]\nport = 9000\nhost = "0.0.0.0"\n')

    assert migrate_legacy_plugin_config(**paths) == ["dashboard"]

    assert _read_toml(target) == {"port": 9999, "host": "0.0.0.0"}
    assert "[dashboard]" not in paths["config_path"].read_text(encoding="utf-8")


def test_noop_when_no_legacy_section(tmp_path: Path) -> None:
    """没有历史分区时不动配置文件、不建插件数据目录。"""
    paths = _paths(tmp_path)
    _write_config(paths["config_path"], "[debug]\nenabled = true\n")
    before = paths["config_path"].read_text(encoding="utf-8")

    assert migrate_legacy_plugin_config(**paths) == []

    assert paths["config_path"].read_text(encoding="utf-8") == before
    assert not paths["data_dir"].exists()
