"""配置迁移"""

import re
from typing import Any

from neobot_app.config.loader import Config


@Config.migration(from_version="0.1.0", to_version="0.2.0")
def migrate_v1_to_v2(old: dict) -> dict:
    """迁移 0.1.0 -> 0.2.0 示例"""
    new: dict[str, Any] = {}

    # 迁移版本号
    new["version"] = "0.2.0"

    # 示例：如果旧版本有 secret_key，迁移到 app.secret_key
    if "secret_key" in old:
        if "app" not in new:
            new["app"] = {}
        new["app"]["secret_key"] = old["secret_key"]

    # 保留其他配置
    for key, value in old.items():
        if key not in ["secret_key", "version"]:
            new[key] = value

    return new


# 提示词系统重构:提示词模板从 config.toml 迁移到独立的提示词文件
# (data/prompts/ 目录,默认+自定义),config.toml 中不再保留提示词键。
# 已自定义过提示词的用户,可在升级后从 config_backup/ 中找回旧值,
# 并手动迁移到 data/prompts/custom/prompts.toml。
_PROMPT_KEYS = frozenset({
    "group_prompt_template",
    "friend_prompt_template",
    "long_reply_fallback_template",
    "group_chat_resume_prompt_template",
})


@Config.migration(from_version="0.3.0", to_version="0.4.0")
def migrate_v3_to_v4(old: dict) -> dict:
    """迁移 0.3.0 -> 0.4.0:清理 config.toml 中的提示词键(已迁移到独立文件)。"""
    new: dict[str, Any] = {"version": "0.4.0"}

    chat = old.get("chat")
    if isinstance(chat, dict):
        chat = {k: v for k, v in chat.items() if k not in _PROMPT_KEYS}
        if chat:
            new["chat"] = chat

    for key, value in old.items():
        if key in ("version", "chat"):
            continue
        new[key] = value

    return new


_LEGACY_ROLE_FIELDS = (
    "primary_chat_model",
    "agent_model_1",
    "agent_model_2",
    "agent_model_3",
    "vision_model",
    "tts_model",
)

_LEGACY_ROLE_DESCRIPTIONS = {
    "primary_chat_model": "主对话模型（Agent模型编号0）",
    "agent_model_1": "Agent模型编号1",
    "agent_model_2": "Agent模型编号2",
    "agent_model_3": "Agent模型编号3",
    "vision_model": "图像识别模型",
    "tts_model": "语音模型",
}


def _default_model_library_map() -> dict[str, dict[str, Any]]:
    """默认模型库：key -> 条目字典（迁移时用于补齐旧配置缺失的角色）。"""
    from dataclasses import asdict

    from neobot_app.config.schemas.bot import _default_model_library

    return {item.key: asdict(item) for item in _default_model_library()}


def _default_role_assignments() -> dict[str, str]:
    """默认调用方引用：角色 -> 默认模型 key。"""
    from neobot_app.config.schemas.bot import ModelAssignments

    return dict(ModelAssignments().items())


def _slug_key(raw: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw or "").strip()).strip("-.")
    return (text or fallback)[:64]


@Config.migration(from_version="0.5.0", to_version="0.6.0")
def migrate_v5_to_v6(old: dict) -> dict:
    """迁移 0.5.0 -> 0.6.0：模型改为「模型库 + 调用方引用 key」。

    - 旧的内联角色配置（primary_chat_model/agent_model_*/vision_model/tts_model/
      creator_image_models）搬进 [[models.registry]]，key 由模型名自动生成；
    - [models.assignments] 记录各调用方引用的 key。
    """
    new: dict[str, Any] = {"version": "0.6.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    legacy_models = old.get("models")
    if not isinstance(legacy_models, dict):
        return new

    library: list[dict[str, Any]] = []
    used_keys: set[str] = set()

    def add_entry(entry: dict[str, Any], fallback_key: str) -> str:
        base = _slug_key(str(entry.get("model_name") or ""), fallback_key)
        key = base
        counter = 2
        while key in used_keys:
            key = f"{base}-{counter}"[:64]
            counter += 1
        used_keys.add(key)
        migrated = {name: value for name, value in entry.items() if name != "key"}
        migrated["key"] = key
        migrated.setdefault("description", _LEGACY_ROLE_DESCRIPTIONS.get(fallback_key, fallback_key))
        library.append(migrated)
        return key

    assignments: dict[str, Any] = {}
    for role in _LEGACY_ROLE_FIELDS:
        entry = legacy_models.get(role)
        if isinstance(entry, dict):
            assignments[role] = add_entry(entry, role)

    legacy_images = legacy_models.get("creator_image_models")
    if isinstance(legacy_images, list):
        image_keys = [
            add_entry(entry, f"image-{index + 1}")
            for index, entry in enumerate(legacy_images)
            if isinstance(entry, dict)
        ]
        if image_keys:
            assignments["creator_image_models"] = image_keys

    # 旧配置可能只写了部分角色：把未出现的角色补回默认模型库条目，
    # 否则 [models.assignments] 的默认值会引用到不存在的 key。
    defaults = _default_model_library_map()
    for role, key in _default_role_assignments().items():
        if role in assignments or key in used_keys:
            continue
        default_entry = defaults.get(key)
        if default_entry is None:
            continue
        used_keys.add(key)
        library.append(dict(default_entry))
        assignments[role] = key

    migrated_models: dict[str, Any] = {}
    if library:
        migrated_models["registry"] = library
    if assignments:
        migrated_models["assignments"] = assignments
    # 保留无法识别的其它模型字段，避免误删用户自定义内容
    for name, value in legacy_models.items():
        if name in _LEGACY_ROLE_FIELDS or name in ("creator_image_models", "registry", "assignments"):
            continue
        migrated_models[name] = value
    if migrated_models:
        new["models"] = migrated_models
    return new


@Config.migration(from_version="0.4.0", to_version="0.5.0")
def migrate_v4_to_v5(old: dict) -> dict:
    """迁移 0.4.0 -> 0.5.0。

    - [console] 双控制台合并为官方 dashboard 插件：面板设置不再写在本体配置里，
      由 plugin_config_migration 在加载配置前搬进插件数据目录，这里只丢弃旧分区。
    - [models.creator_image_model] -> [[models.creator_image_models]]：
      生图模型改为列表，允许配置多个模型/供应商。
    """
    new: dict[str, Any] = {"version": "0.5.0"}

    for key, value in old.items():
        if key in ("version", "console", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if isinstance(models, dict):
        migrated_models = {
            key: value for key, value in models.items() if key != "creator_image_model"
        }
        legacy_image_model = models.get("creator_image_model")
        if isinstance(legacy_image_model, dict):
            migrated_models["creator_image_models"] = [legacy_image_model]
        new["models"] = migrated_models

    return new
