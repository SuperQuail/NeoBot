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
# 缓存目录：可再生的渲染产物（/help 预渲染卡片等），删掉即回退到即时渲染
CACHE_DIR = DATA_DIR / "cache"
# /help 预渲染卡片的缓存目录（spec(5) §4.2 / R9）
HELP_CACHE_DIR = CACHE_DIR / "help"
# 用户头像目录（spec(5) §4.9 / R33–R37）：本体级 AvatarStore 的本地落盘位置
# <DATA_DIR>/avatars/<user_id>.png。目录由 AvatarStore 按需创建（删掉即回到
# 「无本地头像」，下次该用户出现时自动重新获取），因此不在这里预建。
AVATAR_DIR = DATA_DIR / "avatars"
# 插件数据目录：插件配置（config.toml）、独立数据库与鉴权数据都放在各自子目录
PLUGINS_DATA_DIR = DATA_DIR / "plugins_data"
# 插件启停记录：与插件配置解耦的独立状态文件
PLUGIN_STATE_FILE = DATA_DIR / "plugin_state.json"

# 源数据目录（存放模板/教程文档，启动时同步到 DATA_DIR）
SRC_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 确保目录存在
for dir_path in (DATA_DIR, CONFIG_BACKUP_DIR):
    if dir_path.is_file():
        raise FileExistsError(
            f"无法创建目录 '{dir_path}'：该路径已作为文件存在，请手动删除该文件后重试。"
        )
    dir_path.mkdir(parents=True, exist_ok=True)
