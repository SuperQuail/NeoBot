"""配置文件备份工具"""

import datetime
import re
import shutil
from pathlib import Path

from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("config_backup")


def backup_config(file_path: Path, backup_dir: Path, max_backups: int = 15) -> None:
    """备份配置文件到备份目录，保留指定数量的最新备份"""
    if not file_path.exists():
        logger.info(f"配置文件不存在，无需备份: {file_path}")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"config_{timestamp}.toml"
    backup_path = backup_dir / backup_name

    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"配置文件已备份到: {backup_path}")
    except Exception as e:
        logger.error(f"备份配置文件失败: {e}")
        return

    try:
        backup_files = []
        pattern = re.compile(r"^config_\d{8}_\d{6}\.toml$")
        for file in backup_dir.iterdir():
            if file.is_file() and pattern.match(file.name):
                backup_files.append(file)

        backup_files.sort(key=lambda x: x.stat().st_mtime)

        if len(backup_files) > max_backups:
            files_to_delete = backup_files[: len(backup_files) - max_backups]
            for old_file in files_to_delete:
                old_file.unlink()
                logger.info(f"删除旧备份文件: {old_file}")
    except Exception as e:
        logger.error(f"清理旧备份失败: {e}")
