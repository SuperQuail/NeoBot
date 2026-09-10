"""把本体 config.toml 里的官方插件配置搬到插件数据目录（一次性迁移）。

历史上官方插件（dashboard）的配置写在 ``config.toml`` 的同名分区里。
现在插件配置统一落在插件数据目录 ``plugins_data/<插件名>/config.toml``，
插件是否启用则是 ``plugin_state.json`` 里的独立记录，不再出现在任何配置中。

迁移规则（仅当对应分区存在时执行一次）：

1. ``[dashboard]`` 的值写入 ``plugins_data/dashboard/config.toml``；
   更早版本用 ``[console]`` 保存同一批设置，同样按面板字段接收；
   该文件已存在时以文件里的值为准（不覆盖用户已经改过的内容）；
2. ``enabled = false`` 转成插件停用记录（true / 缺省不写记录，默认启用）；
3. 从 config.toml 删除这些历史分区（改动前备份到 ``config_backup/``）。

任何一步失败都不阻断启动：记录告警后保持原样，插件按默认值运行。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import tomlkit

from neobot_app.core import (
    CONFIG_BACKUP_DIR,
    CONFIG_FILE,
    PLUGIN_STATE_FILE,
    PLUGINS_DATA_DIR,
)
from neobot_app.config.loader.backup import backup_config
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_modloader import PLUGIN_CONFIG_FILENAME, PluginStateStore

#: 插件名 -> config.toml 里的历史分区（按优先级排列，取第一个存在的）
LEGACY_SECTIONS: dict[str, tuple[str, ...]] = {"dashboard": ("dashboard", "console")}

#: [console] 里的旧字段 -> 面板配置字段（控制台合并进面板时沿用下来的字段）
_CONSOLE_CARRY_KEYS: dict[str, str] = {
    "enabled": "enabled",
    "host": "host",
    "port": "port",
    "session_timeout_minutes": "session_timeout_minutes",
    "secure_cookies": "secure_cookies",
    "trust_proxy_headers": "trust_proxy_headers",
}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def plugin_config_file(plugin_name: str, *, data_dir: Path | None = None) -> Path:
    """插件配置文件的规范位置。"""
    root = Path(data_dir) if data_dir is not None else PLUGINS_DATA_DIR
    return root / plugin_name / PLUGIN_CONFIG_FILENAME


def migrate_legacy_plugin_config(
    *,
    config_path: Path | None = None,
    data_dir: Path | None = None,
    backup_dir: Path | None = None,
    state_file: Path | None = None,
    logger: Logger | None = None,
) -> list[str]:
    """执行迁移，返回被迁移的插件名列表（没有可迁移内容时返回空列表）。"""
    log = logger or NullLogger()
    source = Path(config_path) if config_path is not None else CONFIG_FILE
    if not source.is_file():
        return []
    try:
        document = tomlkit.parse(source.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        log.warning(f"读取 config.toml 失败，跳过官方插件配置迁移: {exc}")
        return []

    migrated: list[str] = []
    for plugin_name, sections in LEGACY_SECTIONS.items():
        present = [name for name in sections if name in document]
        if not present:
            continue
        source_section = present[0]
        table = document[source_section]
        if not hasattr(table, "unwrap"):
            continue
        try:
            values: dict[str, Any] = dict(table.unwrap())
        except Exception as exc:
            log.warning(f"解析 config.toml 的 [{source_section}] 失败，保持原样: {exc}")
            continue
        if source_section == "console":
            # 旧控制台分区里有面板不认识的字段（admin_* 等），只带走面板自己的
            values = {
                _CONSOLE_CARRY_KEYS[key]: value
                for key, value in values.items()
                if key in _CONSOLE_CARRY_KEYS
            }
        # 是否启用不是配置项：false 记入 plugin_state.json，true/缺省不写
        enabled = values.pop("enabled", None)
        if enabled is False:
            try:
                PluginStateStore(
                    Path(state_file) if state_file is not None else PLUGIN_STATE_FILE,
                    logger=log,
                ).set_enabled(plugin_name, False)
            except Exception as exc:
                log.warning(f"写入插件停用记录失败 ({plugin_name}): {exc}")
        target = plugin_config_file(plugin_name, data_dir=data_dir)
        try:
            stored: dict[str, Any] = {}
            if target.is_file():
                stored = dict(tomlkit.parse(target.read_text(encoding="utf-8-sig")).unwrap())
            merged = {**values, **stored}
            if merged or not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                body = tomlkit.document()
                for key, value in merged.items():
                    body[key] = tomlkit.item(value)
                _atomic_write(target, tomlkit.dumps(body))
        except Exception as exc:
            log.warning(f"写入插件配置失败 ({plugin_name})，保持 config.toml 原样: {exc}")
            continue
        for name in present:
            document.pop(name, None)
        migrated.append(plugin_name)
        log.info(
            f"官方插件配置已迁移到插件数据目录: {plugin_name}",
            config=str(target),
        )

    if not migrated:
        return []
    try:
        backup_config(source, Path(backup_dir) if backup_dir is not None else CONFIG_BACKUP_DIR)
        _atomic_write(source, tomlkit.dumps(document))
    except Exception as exc:
        log.warning(f"清理 config.toml 中的历史分区失败（配置值已迁移）: {exc}")
    return migrated
