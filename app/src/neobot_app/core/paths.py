"""路径管理函数"""

import os
import sys
from pathlib import Path


def _is_packaged() -> bool:
    """检测是否为打包后的可执行文件"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_project_root() -> Path:
    """获取项目根目录（仅开发环境）"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists():
            return parent
    root = None
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            root = parent
    return root if root else Path.cwd()


def get_data_dir() -> Path:
    """获取数据目录"""
    if env_dir := os.getenv("NEOBOT_DATA_DIR"):
        return Path(env_dir)
    if _is_packaged():
        exe_dir = Path(sys.executable).parent
        data_dir = exe_dir / "data"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            test_file = data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return data_dir
        except (PermissionError, OSError):
            return Path.home() / ".neobot" / "data"
    return _get_project_root() / "app" / "data"


def get_env_file() -> Path:
    """获取环境变量文件"""
    if env_file := os.getenv("NEOBOT_ENV_FILE"):
        return Path(env_file)
    if _is_packaged():
        return Path(sys.executable).parent / ".env"
    return _get_project_root() / "app" / ".env"
