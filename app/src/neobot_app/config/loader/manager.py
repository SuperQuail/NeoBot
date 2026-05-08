"""配置加载器"""

import sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, Type, TypeVar

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass
from neobot_app.core import CONFIG_BACKUP_DIR
from neobot_app.utils.logger import get_module_logger

T = TypeVar("T")
logger = get_module_logger("config_loader")


def _build_provider_extra_body(
    provider_name: str,
    settings_config: Any,
) -> dict[str, Any]:
    if settings_config is None:
        return {}

    provider_kind = provider_name.strip().casefold().replace("-", "_")
    if provider_kind not in {"deepseek", "deepseek_offical", "deepseek_official"}:
        return {}

    thinking_mode = _normalize_deepseek_thinking_mode(
        getattr(settings_config, "deepseek_thinking_mode", True)
    )

    reasoning_effort = str(
        getattr(settings_config, "deepseek_reasoning_effort", "high")
    ).strip().casefold()

    probability = getattr(settings_config, "deepseek_random_thinking_probability", 0.6)
    try:
        random_probability = float(probability)
    except (TypeError, ValueError):
        random_probability = 0.6
    random_probability = max(0.0, min(1.0, random_probability))

    return {
        "__deepseek_thinking_mode__": thinking_mode,
        "__deepseek_reasoning_effort__": reasoning_effort,
        "__deepseek_random_thinking_probability__": random_probability,
    }


def _normalize_deepseek_thinking_mode(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "on", "enabled", "enable"}:
        return "true"
    if normalized in {"random"}:
        return "random"
    return "false"


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
    def register_models(cls, config_obj: Any):
        """根据配置自动注册模型。"""
        models_config = getattr(config_obj, "models", None)
        if models_config is None:
            return None

        if not is_dataclass(models_config):
            raise TypeError("config.models 必须是 dataclass")

        from neobot_app.config.schemas.env import EnvConfig
        from neobot_chat import (
            ModelPricing,
            ModelSettings,
            RegisteredModel,
            get_model_registry,
        )

        registry = get_model_registry()
        registry.clear()

        registered_count = 0
        for model_field in fields(models_config):
            model_config = getattr(models_config, model_field.name)
            if not is_dataclass(model_config):
                continue
            creator_config = getattr(getattr(config_obj, "agent", None), "creator", None)
            if (
                model_field.name == "creator_image_model"
                and not getattr(creator_config, "enabled", False)
            ):
                logger.info("Creator Agent 未启用，跳过注册 creator_image_model")
                continue

            provider_name = getattr(model_config, "provider", "").strip()
            model_name = getattr(model_config, "model_name", "").strip()
            description = getattr(model_config, "description", model_field.name).strip()
            if (
                model_field.name == "primary_chat_model"
                and "模型编号0" not in description
            ):
                description = f"{description}（Agent模型编号0）"
            if not provider_name:
                raise ValueError(f"模型 {model_field.name} 缺少 provider 配置")
            if not model_name:
                raise ValueError(f"模型 {model_field.name} 缺少 model_name 配置")

            platform_config = EnvConfig.get_api_platform_config(provider_name)
            if not platform_config.url:
                raise ValueError(
                    f"模型 {model_field.name} 缺少平台 {provider_name}_URL 配置"
                )
            if not platform_config.api_key:
                raise ValueError(
                    f"模型 {model_field.name} 缺少平台 {provider_name}_APIKey 配置"
                )

            pricing_config = getattr(model_config, "pricing", None)
            settings_config = getattr(model_config, "settings", None)
            pricing = ModelPricing(
                input_price_per_mtokens=getattr(
                    pricing_config, "input_price_per_mtokens", 0.0
                ),
                output_price_per_mtokens=getattr(
                    pricing_config, "output_price_per_mtokens", 0.0
                ),
                cache_hit_price_per_mtokens=getattr(
                    pricing_config, "cache_hit_price_per_mtokens", 0.0
                ),
                billing_metric=getattr(pricing_config, "billing_metric", ""),
            )
            settings = ModelSettings(
                temperature=getattr(settings_config, "temperature", None),
                max_output_tokens=getattr(settings_config, "max_output_tokens", None),
                timeout_seconds=getattr(settings_config, "timeout_seconds", 120.0),
                top_p=getattr(settings_config, "top_p", None),
                frequency_penalty=getattr(
                    settings_config, "frequency_penalty", None
                ),
                presence_penalty=getattr(settings_config, "presence_penalty", None),
                extra_body=_build_provider_extra_body(provider_name, settings_config),
            )

            registry.register(
                RegisteredModel(
                    name=model_field.name,
                    description=description,
                    provider_name=provider_name,
                    model_name=model_name,
                    base_url=platform_config.url,
                    api_key=platform_config.api_key,
                    pricing=pricing,
                    settings=settings,
                )
            )
            registered_count += 1
            logger.info(
                f"已注册模型: {model_field.name} -> {provider_name}/{model_name}"
            )

        logger.info(f"模型注册完成，共注册 {registered_count} 个模型")
        return registry

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
            cls.register_models(config_obj)
            return config_obj
        except Exception as e:
            logger.error(f"解析配置文件失败: {e}")
            sys.exit(1)
