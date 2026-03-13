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
        existing_keys = set()
        lines = []
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                lines.append(line.rstrip('\n'))
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    existing_keys.add(key)
                    os.environ[key] = _
        logger.info(f"环境变量文件 {ENV_FILE} 加载完毕")

        # 检查缺失的配置字段
        missing_fields = []
        fields = EnvConfig.__dataclass_fields__
        for field_name, field_obj in fields.items():
            env_key = field_name.upper()
            if env_key not in existing_keys:
                # 获取字段信息
                field_type = field_obj.type
                optional = get_origin(field_type) is Union and type(None) in get_args(field_type)
                required = not optional
                description = field_obj.metadata.get("description", "")
                default = field_obj.default if field_obj.default is not MISSING else None
                default_str = "" if default is None or default is MISSING else str(default)

                # 记录错误日志
                logger.error(
                    f"环境变量文件中缺失配置字段: {env_key} "
                    f"[{'必须项' if required else '非必须项'}] {description}"
                )

                # 准备追加的行
                comment_line = f"#{description} [{'必须项' if required else '非必须项'}]\n"
                value_line = f"{env_key}={default_str}"
                missing_fields.append((comment_line, value_line))

        # 如果有缺失字段，追加到文件末尾
        if missing_fields:
            try:
                with open(ENV_FILE, "a", encoding="utf-8") as f:
                    # 确保追加前文件末尾有换行
                    if lines and not lines[-1].endswith("\n"):
                        f.write("\n")
                    for comment_line, value_line in missing_fields:
                        f.write(f"\n{comment_line}{value_line}")
                logger.warning(f"已补充缺失的配置字段到环境变量文件: {ENV_FILE}")
            except Exception as e:
                logger.error(f"补充缺失配置字段失败: {e}")
    else:
        logger.info("环境变量文件不存在")
        generate_env()
        logger.info("请手动填写环境变量文件再重启")
