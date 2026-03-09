"""配置加载器"""

import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Tuple, Type, TypeVar

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass
from neobot_app.core import CONFIG_FILE, CONFIG_BACKUP_DIR
from neobot_app.utils.logger import get_module_logger

T = TypeVar("T")
logger = get_module_logger("config_loader")


def _check_placeholders(obj: Any, path: str = "") -> list[str]:
    """递归检查配置对象中的占位符值"""
    from dataclasses import is_dataclass

    placeholders = []
    if not is_dataclass(obj):
        return placeholders

    for field in fields(obj):
        field_path = f"{path}.{field.name}" if path else field.name
        value = getattr(obj, field.name)

        # 检查是否标记为占位符
        if field.metadata.get("placeholder") and value == field.default:
            placeholders.append(field_path)

        # 递归检查嵌套对象
        if is_dataclass(value):
            placeholders.extend(_check_placeholders(value, field_path))

    return placeholders


class Config:
    """配置管理类"""

    _migrations: Dict[Tuple[str, str], Any] = {}

    @classmethod
    def migration(cls, from_version: str, to_version: str):
        """配置迁移装饰器"""

        def decorator(func):
            cls._migrations[(from_version, to_version)] = func
            return func

        return decorator

    @classmethod
    def _apply_migrations(
        cls, data: dict, current_version: str, target_version: str
    ) -> dict:
        """应用配置迁移"""
        if current_version == target_version:
            return data

        migration_key = (current_version, target_version)
        if migration_key in cls._migrations:
            logger.info(f"应用配置迁移: {current_version} -> {target_version}")
            return cls._migrations[migration_key](data)

        logger.warning(f"未找到迁移路径: {current_version} -> {target_version}")
        return data

    @classmethod
    def load(cls, file_path: Path, schema: Type[T]) -> T:
        """加载配置文件，如果不存在则生成，如果存在则检查并补全缺失项"""
        logger.info(f"加载配置文件: {file_path}")

        existing_data: dict[Any, Any] = {}
        file_exists = file_path.exists()

        if file_exists:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_data = tomlkit.parse(f.read()).unwrap()
                logger.info(f"配置文件已读取: {file_path}")

                current_version = existing_data.get("version")
                target_version = getattr(schema(), "version", None)
                if (
                    current_version
                    and target_version
                    and current_version != target_version
                ):
                    logger.info(
                        f"检测到配置版本变化: {current_version} -> {target_version}"
                    )
                    existing_data = cls._apply_migrations(
                        existing_data, current_version, target_version
                    )
            except Exception as e:
                logger.error(f"读取配置文件失败: {e}")
                existing_data = {}

        toml_doc, missing_required, missing_optional = dataclass_to_toml(
            schema, existing_data if file_exists else None, is_root=True
        )

        # 只在首次生成或有缺失项时写入文件
        should_write = not file_exists or missing_required or missing_optional

        if should_write:
            if missing_required:
                for field in missing_required:
                    logger.warning(f"缺失必须配置项: {field}")
            if missing_optional:
                for field in missing_optional:
                    logger.info(f"缺失非必须配置项: {field}")

            if file_exists:
                backup_config(file_path, CONFIG_BACKUP_DIR)

            assert toml_doc is not None, "toml_doc should not be None for valid dataclass"
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(tomlkit.dumps(toml_doc))
                logger.info(
                    f"配置文件已{'更新并补全缺失项' if file_exists else '生成'}: {file_path}"
                )
            except Exception as e:
                logger.error(f"写入配置文件失败: {e}")
                if not file_exists:
                    logger.error("无法生成配置文件，程序退出")
                    sys.exit(1)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config_dict = tomlkit.parse(f.read()).unwrap()
            config_obj = dict_to_dataclass(config_dict, schema)

            # 检查占位符值
            placeholders = _check_placeholders(config_obj)
            if placeholders:
                logger.warning("以下配置项使用了占位符值，请修改为实际值:")
                for field in placeholders:
                    logger.warning(f"  - {field}")

            logger.info("配置文件加载成功")
            return config_obj
        except Exception as e:
            logger.error(f"解析配置文件失败: {e}")
            sys.exit(1)
