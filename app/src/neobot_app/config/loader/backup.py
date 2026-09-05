"""配置文件备份工具"""

import re
import shutil
import time
from pathlib import Path

from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("config_backup")


def backup_config(file_path: Path, backup_dir: Path, max_backups: int = 15) -> None:
    """备份配置文件到备份目录，保留指定数量的最新备份"""
    if not file_path.exists():
        logger.info(f"配置文件不存在，无需备份: {file_path}")
        return

    # 毫秒级时间戳,避免同一秒内多次备份互相覆盖
    timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
    backup_name = f"config_{timestamp}.toml"
    backup_path = backup_dir / backup_name

    try:
        # 备份目录可能被清空/权限异常,先确保存在
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        logger.info(f"配置文件已备份到: {backup_path}")
    except Exception as e:
        logger.error(f"备份配置文件失败: {e}")
        return

    try:
        backup_files = []
        pattern = re.compile(r"^config_\d{8}_\d{6}(?:_\d{3})?\.toml$")
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
