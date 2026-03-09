"""环境变量加载工具"""

import os
from dataclasses import MISSING
from typing import Union, get_args, get_origin

from neobot_app.config.schemas.env import EnvConfig
from neobot_app.core import ENV_FILE
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("config_env")


def generate_env():
    """生成环境变量模板"""
    logger.info("尝试生成环境变量模板...")
    fields = EnvConfig.__dataclass_fields__
    lines = []
    for field_name, field_obj in fields.items():
        field_type = field_obj.type
        optional = get_origin(field_type) is Union and type(None) in get_args(
            field_type
        )
        required = not optional
        description = field_obj.metadata.get("description", "")
        default = field_obj.default if field_obj.default is not MISSING else None
        env_key = field_name.upper()
        default_str = "" if default is None or default is MISSING else str(default)
        line = f"#{description} [{'必须项' if required else '非必须项'}]\n{env_key}={default_str}"
        lines.append(line)

    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"环境变量模板已生成: {ENV_FILE}")
    except Exception as e:
        logger.error(f"生成环境变量模板失败: {e}")


def load_env():
    """加载环境变量"""
    logger.info("尝试加载环境变量...")
    if ENV_FILE.exists():
        logger.info(f"环境变量文件 {ENV_FILE} 存在，开始加载...")
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                key, value = line.split("=", 1)
                os.environ[key] = value
        logger.info(f"环境变量文件 {ENV_FILE} 加载完毕")
    else:
        logger.info("环境变量文件不存在")
        generate_env()
        logger.info("请手动填写环境变量文件再重启")
