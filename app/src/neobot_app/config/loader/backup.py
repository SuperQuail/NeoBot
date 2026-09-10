"""配置文件备份工具"""

import re
import shutil
import time
from pathlib import Path

from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("config_backup")

#: 备份文件名：``<源文件名>_<时间戳>.<原后缀>``（时间戳精确到毫秒，避免同秒覆盖）
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def backup_config(file_path: Path, backup_dir: Path, max_backups: int = 15) -> None:
    """备份配置文件到备份目录，保留指定数量的最新备份。

    备份名带上源文件名：备份目录里同时存在 config.toml 与 .env 的备份，
    之前两者都叫 ``config_<ts>.toml``（.env 的明文密钥被写进名为 config 的文件），
    既容易误把 .env 备份当配置还原，也会让两类备份互相挤占保留额度。
    """
    if not file_path.exists():
        logger.info(f"配置文件不存在，无需备份: {file_path}")
        return

    timestamp = time.strftime(_TIMESTAMP_FORMAT) + f"_{int(time.time() * 1000) % 1000:03d}"
    name = file_path.name
    suffix = file_path.suffix
    stem = name[: -len(suffix)] if suffix else name
    backup_path = backup_dir / f"{stem}_{timestamp}{suffix}"

    try:
        # 备份目录可能被清空/权限异常,先确保存在
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        logger.info(f"配置文件已备份到: {backup_path}")
    except Exception as e:
        logger.error(f"备份配置文件失败: {e}")
        return

    try:
        # 只轮转同一来源的备份：不同来源各自保留 max_backups 份
        pattern = re.compile(
            rf"^{re.escape(stem)}_\d{{8}}_\d{{6}}(?:_\d{{3}})?{re.escape(suffix)}$"
        )
        backup_files = [
            file
            for file in backup_dir.iterdir()
            if file.is_file() and pattern.match(file.name)
        ]
        backup_files.sort(key=lambda x: x.stat().st_mtime)

        if len(backup_files) > max_backups:
            for old_file in backup_files[: len(backup_files) - max_backups]:
                old_file.unlink()
                logger.info(f"删除旧备份文件: {old_file}")
    except Exception as e:
        logger.error(f"清理旧备份失败: {e}")
