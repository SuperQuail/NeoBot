"""常量定义"""

from importlib.metadata import version, PackageNotFoundError

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

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
