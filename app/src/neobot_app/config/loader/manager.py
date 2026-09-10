"""配置加载器"""

import os
import tempfile
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, Type, TypeVar

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass
from neobot_app.utils.logger import get_module_logger

T = TypeVar("T")
logger = get_module_logger("config_loader")


class ConfigLoadError(RuntimeError):
    """配置加载失败（缺失必需配置项、无法生成配置文件等）。

    由调用方决定处理方式：启动路径可以打印清单后退出，
    reload 路径应记录错误并保持旧配置生效。
    """


def _atomic_write_text(path: Path, text: str) -> None:
    """原子写入文本文件（同目录临时文件 + fsync + os.replace）。

    config.toml 有三个写入者（本模块、面板、命令系统），直接 `open(w)`
    截断写在崩溃/并发下可能留下半截文件，下次启动即解析失败。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


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
    def _resolve_migration_chain(
        cls, current_version: str, target_version: str
    ) -> list[tuple[str, str]]:
        """解析 current -> target 的迁移链（支持多步迁移，如 0.3.0->0.4.0->0.5.0）。"""
        chain: list[tuple[str, str]] = []
        version = current_version
        seen: set[str] = set()
        while version != target_version:
            if version in seen:
                return []
            seen.add(version)
            candidates = [pair for pair in cls._migrations if pair[0] == version]
            if not candidates:
                return []
            # 优先直达目标版本，否则按版本号排序取下一步
            candidates.sort(key=lambda pair: (pair[1] != target_version, pair[1]))
            step = candidates[0]
            chain.append(step)
            version = step[1]
        return chain

    @classmethod
    def _apply_migrations(
        cls, data: dict, current_version: str, target_version: str
    ) -> dict:
        """应用配置迁移（逐级链式执行，保证跨多个版本升级也能正确迁移）。"""
        if current_version == target_version:
            return data

        chain = cls._resolve_migration_chain(current_version, target_version)
        if not chain:
            logger.warning(f"未找到迁移路径: {current_version} -> {target_version}")
            return data

        migrated = data
        for from_version, to_version in chain:
            logger.info(f"应用配置迁移: {from_version} -> {to_version}")
            migrated = cls._migrations[(from_version, to_version)](migrated)
            if not isinstance(migrated, dict):
                raise TypeError(
                    f"配置迁移 {from_version} -> {to_version} 必须返回 dict"
                )
            # 迁移函数可能忘记写版本号，这里强制推进，避免链式迁移卡住
            migrated["version"] = to_version
        return migrated

    @classmethod
    def register_models(cls, config_obj: Any):
        """根据「模型库 + 调用方引用」注册模型。

        每个模型库条目按 key 注册一次；调用方（主对话/Agent/视觉/TTS/生图）
        只引用 key。未启用功能的模型（creator_image_models、tts_model）跳过注册与
        Key 校验；无启用开关的模型（vision_model）缺 Key 时降级跳过并警告；
        必需对话模型缺 Key 时收集全部缺失项后抛出 ConfigLoadError。
        """
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

        # 无独立 enabled 开关、缺 Key 时可降级跳过的角色
        degradable_roles = {"vision_model", "tts_model"}

        def _feature_enabled(role: str) -> bool:
            if role == "tts_model":
                return bool(getattr(getattr(config_obj, "tts", None), "enabled", False))
            if role == "creator_image_models":
                return bool(
                    getattr(getattr(config_obj, "agent", None), "creator", None)
                    and getattr(
                        getattr(config_obj, "agent", None).creator, "enabled", False
                    )
                )
            return True

        registry = get_model_registry()

        pending: list[tuple] = []
        missing_items: list[str] = []

        # 调用方引用了模型库里不存在的 key：必需角色报错，可降级角色仅告警
        library_keys = (
            set(models_config.by_key()) if hasattr(models_config, "by_key") else set()
        )
        assignments = getattr(models_config, "assignments", None)
        if assignments is not None and hasattr(assignments, "items"):
            for ref_role, ref_key in assignments.items():
                if ref_key in library_keys:
                    continue
                if not _feature_enabled(ref_role):
                    logger.info(f"{ref_role} 对应功能未启用，跳过缺失模型检查: {ref_key}")
                    continue
                detail = f"调用方 {ref_role} 引用了模型库中不存在的 key: {ref_key}"
                if ref_role in degradable_roles:
                    logger.warning(f"{detail}，该功能将被降级禁用")
                    continue
                missing_items.append(detail)

        iter_role_models = getattr(models_config, "iter_role_models", None)
        if callable(iter_role_models):
            registrations = list(iter_role_models())
        else:
            registrations = [
                (item.name, getattr(models_config, item.name))
                for item in fields(models_config)
                if is_dataclass(getattr(models_config, item.name))
            ]

        registered_keys: set[str] = set()
        for role, model_config in registrations:
            if not is_dataclass(model_config):
                continue
            if not _feature_enabled(role):
                logger.info(f"{role} 对应功能未启用，跳过注册与校验")
                continue

            key = str(getattr(model_config, "key", "") or "").strip()
            if not key:
                missing_items.append(f"{role} 引用的模型缺少 key（模型库条目的 key 不能为空）")
                continue
            if key in registered_keys:
                continue

            provider_name = getattr(model_config, "provider", "").strip()
            model_name = getattr(model_config, "model_name", "").strip()
            description = getattr(model_config, "description", key).strip()
            if role == "primary_chat_model" and "模型编号0" not in description:
                description = f"{description}（Agent模型编号0）"

            missing: list[str] = []
            if not provider_name:
                missing.append("provider 配置")
            if not model_name:
                missing.append("model_name 配置")

            platform_config = None
            if provider_name:
                platform_config = EnvConfig.get_api_platform_config(provider_name)
                if not platform_config.url:
                    missing.append(f"平台 {provider_name}_URL 配置")
                if not platform_config.api_key:
                    missing.append(f"平台 {provider_name}_APIKey 配置")

            if missing:
                detail = f"模型 {key}（{role}）缺少: " + "、".join(missing)
                if role in degradable_roles:
                    logger.warning(f"{detail}，该功能将被降级禁用")
                    continue
                missing_items.append(detail)
                continue
            registered_keys.add(key)

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
                image_api=str(getattr(settings_config, "image_api", "auto") or "auto"),
                image_reference_param=str(
                    getattr(settings_config, "image_reference_param", "image") or "image"
                ),
            )
            pending.append(
                (
                    key,
                    description,
                    provider_name,
                    model_name,
                    platform_config,
                    pricing,
                    settings,
                    bool(getattr(model_config, "native_vision", False)),
                    bool(getattr(model_config, "use_system_proxy", False)),
                    str(getattr(model_config, "model_type", "chat") or "chat"),
                )
            )

        if missing_items:
            message = (
                "配置校验失败，以下必需配置缺失（请补充对应平台的环境变量）：\n"
                + "\n".join(f"  - {item}" for item in missing_items)
            )
            logger.error(message)
            raise ConfigLoadError(message)

        registry.clear()

        registered_count = 0
        for (
            name,
            description,
            provider_name,
            model_name,
            platform_config,
            pricing,
            settings,
            native_vision,
            use_system_proxy,
            model_type,
        ) in pending:
            registry.register(
                RegisteredModel(
                    name=name,
                    description=description,
                    provider_name=provider_name,
                    model_name=model_name,
                    base_url=platform_config.url,
                    api_key=platform_config.api_key,
                    pricing=pricing,
                    settings=settings,
                    native_vision=native_vision,
                    use_system_proxy=use_system_proxy,
                    model_type=model_type,
                )
            )
            registered_count += 1
            logger.info(
                f"已注册模型: {name} -> {provider_name}/{model_name}"
            )

        logger.info(f"模型注册完成，共注册 {registered_count} 个模型")
        return registry

    @classmethod
    def load(cls, file_path: Path, schema: Type[T]) -> T:
        """加载配置文件，如果不存在则生成，如果存在则检查并补全缺失项"""
        # 注册配置迁移(migrate_* 装饰器在 import 时注册)。
        # 必须在首次 load 前完成;懒加载避免模块初始化阶段的循环依赖。
        from neobot_app.config import migrations as _migrations  # noqa: F401

        logger.info(f"加载配置文件: {file_path}")

        existing_data: dict[Any, Any] = {}
        file_exists = file_path.exists()
        load_error: Exception | None = None

        if file_exists:
            try:
                # utf-8-sig 兼容 Windows 记事本保存的 UTF-8 BOM(否则 tomlkit 抛
                # EmptyKeyError,整份配置会被当作损坏重置为默认值,造成数据丢失)
                with open(file_path, "r", encoding="utf-8-sig") as f:
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
                load_error = e
                existing_data = {}

        if load_error is not None:
            # 解析失败时绝不能继续走「补全缺失项 → 写回」：dataclass_to_toml 会把
            # schema 的所有字段都当成缺失项，等于用默认值整份覆盖用户配置
            # （只有 config_backup/ 能人工救回）。宁可启动失败并报出原因。
            raise ConfigLoadError(
                f"配置文件解析失败，已保持原文件不变：{file_path}\n"
                f"原因: {load_error}\n"
                "请修复该文件（或先移走它重新生成）后重试。"
            )

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
                # 备份目录按配置文件位置派生:生产环境等价于全局
                # CONFIG_BACKUP_DIR(DATA_DIR/config_backup),同时隔离测试/
                # 外部工具对真实备份目录的污染与误删
                backup_config(file_path, file_path.parent / "config_backup")

            assert toml_doc is not None, "toml_doc should not be None for valid dataclass"
            try:
                _atomic_write_text(file_path, tomlkit.dumps(toml_doc))
                logger.info(
                    f"配置文件已{'更新并补全缺失项' if file_exists else '生成'}: {file_path}"
                )
            except Exception as e:
                logger.error(f"写入配置文件失败: {e}")
                if not file_exists:
                    logger.error("无法生成配置文件")
                    raise ConfigLoadError(
                        f"无法生成配置文件 {file_path}，请检查目录写入权限"
                    ) from e

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
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
        except ConfigLoadError:
            raise
        except Exception as e:
            logger.error(f"解析配置文件失败: {e}")
            raise
