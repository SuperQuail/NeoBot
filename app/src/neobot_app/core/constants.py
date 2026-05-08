"""常量定义"""

from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from neobot_app.core.paths import get_data_dir, get_env_file


def _get_version() -> str:
    """获取应用版本号"""
    try:
        return version("neobot-app")
    except PackageNotFoundError:
        return "0.0.0"


# 应用信息
APP_NAME = "NeoBot"
APP_VERSION = _get_version()

# 配置相关
MAX_CONFIG_BACKUPS = 15
CONFIG_VERSION = APP_VERSION

# 路径常量
DATA_DIR = get_data_dir()
ENV_FILE = get_env_file()
CONFIG_FILE = DATA_DIR / "config.toml"
CONFIG_BACKUP_DIR = DATA_DIR / "config_backup"

# 源数据目录（存放模板/教程文档，启动时同步到 DATA_DIR）
SRC_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 确保目录存在
for dir_path in (DATA_DIR, CONFIG_BACKUP_DIR):
    if dir_path.is_file():
        raise FileExistsError(
            f"无法创建目录 '{dir_path}'：该路径已作为文件存在，请手动删除该文件后重试。"
        )
    dir_path.mkdir(parents=True, exist_ok=True)
