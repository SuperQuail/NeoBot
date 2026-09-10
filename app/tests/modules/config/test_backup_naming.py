"""备份命名必须区分来源文件。

同一备份目录里既有 config.toml 也有 .env 的备份时，旧实现把两者都命名为
``config_<ts>.toml``：.env 的明文密钥落在名为 config 的文件里（极易被误当配置
还原），两类备份还会互相挤占保留额度。
"""

from __future__ import annotations

import time
from pathlib import Path

from neobot_app.config.loader.backup import backup_config


def test_backup_name_carries_source_name(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('version = "1.0.0"\n', encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("DeepSeek_APIKey=sk-test\n", encoding="utf-8")
    backup_dir = tmp_path / "config_backup"

    backup_config(config_file, backup_dir)
    backup_config(env_file, backup_dir)

    names = sorted(p.name for p in backup_dir.iterdir())
    assert any(name.startswith("config_") and name.endswith(".toml") for name in names)
    assert any(name.startswith(".env_") for name in names)
    # .env 的备份不能再伪装成 config.toml
    assert len([n for n in names if n.endswith(".toml")]) == 1


def test_rotation_is_per_source(tmp_path: Path) -> None:
    """不同来源各自保留 max_backups 份，不互相挤占。"""
    config_file = tmp_path / "config.toml"
    config_file.write_text("a = 1\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    backup_dir = tmp_path / "config_backup"

    # 备份名的时间戳精确到毫秒，稍作间隔避免同毫秒互相覆盖
    for _ in range(3):
        backup_config(config_file, backup_dir, max_backups=2)
        time.sleep(0.005)
    for _ in range(3):
        backup_config(env_file, backup_dir, max_backups=2)
        time.sleep(0.005)

    names = [p.name for p in backup_dir.iterdir()]
    assert len([n for n in names if n.endswith(".toml")]) == 2
    assert len([n for n in names if n.startswith(".env_")]) == 2


def test_missing_source_is_noop(tmp_path: Path) -> None:
    backup_dir = tmp_path / "config_backup"

    backup_config(tmp_path / "nope.toml", backup_dir)

    assert not backup_dir.exists()
