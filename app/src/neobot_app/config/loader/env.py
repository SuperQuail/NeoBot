"""环境变量加载工具。"""

import os
from dataclasses import MISSING
from typing import Union, get_args, get_origin

from neobot_app.config.schemas.env import EnvConfig
from neobot_app.core import ENV_FILE
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("config_env")


def _is_required(field_obj) -> bool:
    field_type = field_obj.type
    optional = get_origin(field_type) is Union and type(None) in get_args(field_type)
    return not optional


def _get_env_key(field_name: str, field_obj) -> str:
    return field_obj.metadata.get("env_key", field_name.upper())


def _build_env_lines(field_name: str, field_obj) -> list[str]:
    required = _is_required(field_obj)
    description = field_obj.metadata.get("description", "")
    comment_lines = field_obj.metadata.get("comment_lines", [])
    default = field_obj.default if field_obj.default is not MISSING else None
    default_str = "" if default is None or default is MISSING else str(default)
    env_key = _get_env_key(field_name, field_obj)

    lines = [f"#{description} [{'必须项' if required else '非必须项'}]"]
    lines.extend(f"#{comment}" for comment in comment_lines if comment)
    lines.append(f"{env_key}={default_str}")
    return lines


def _contains_env_key(existing_keys: set[str], env_key: str) -> bool:
    target = env_key.casefold()
    return any(key.casefold() == target for key in existing_keys)


def generate_env():
    """生成环境变量模板。"""
    fields = EnvConfig.__dataclass_fields__
    blocks = ["\n".join(_build_env_lines(field_name, field_obj)) for field_name, field_obj in fields.items()]

    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(blocks))
        logger.info("环境变量模板已生成", event="config.env_created", path=str(ENV_FILE))
    except Exception as e:
        logger.error(f"生成环境变量模板失败: {e}")


def load_env():
    """加载环境变量。"""
    if ENV_FILE.exists():
        existing_keys: set[str] = set()
        lines: list[str] = []

        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                lines.append(line.rstrip("\n"))
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if "=" in stripped:
                    key, value = (part.strip() for part in stripped.split("=", 1))
                    if not key:
                        logger.warning(f"忽略无效的环境变量行（键为空）: line={line_number}")
                        continue
                    existing_keys.add(key)
                    os.environ[key] = value

        missing_blocks: list[str] = []
        missing_keys: list[str] = []
        fields = EnvConfig.__dataclass_fields__
        for field_name, field_obj in fields.items():
            env_key = _get_env_key(field_name, field_obj)
            if _contains_env_key(existing_keys, env_key):
                continue

            missing_keys.append(env_key)
            missing_blocks.append("\n".join(_build_env_lines(field_name, field_obj)))

        if missing_blocks:
            try:
                with open(ENV_FILE, "a", encoding="utf-8") as f:
                    if lines:
                        f.write("\n")
                    for block in missing_blocks:
                        f.write(f"\n{block}")
                logger.info(
                    "环境变量模板已补全，新增字段待按需填写",
                    event="config.env_extended",
                    path=str(ENV_FILE),
                    added_keys=missing_keys,
                )
            except Exception as e:
                logger.error(f"补全缺失配置字段失败: {e}")
    else:
        generate_env()
        logger.info("请按需填写环境变量文件后重启", path=str(ENV_FILE))
