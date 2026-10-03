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
    """默认模型库：引用名 -> 条目字典（迁移时用于补齐旧配置缺失的角色）。"""
    from dataclasses import asdict

    from neobot_app.config.schemas.bot import _default_model_library

    return {item.model_ref: asdict(item) for item in _default_model_library()}


def _default_role_assignments() -> dict[str, str]:
    """默认调用方引用：角色 -> 默认模型条目引用名。"""
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


#: 旧的默认对话模型 key -> 新 key。这些 key 一开始由 model_name 自动生成，当时
#: DeepSeek 侧确实叫 deepseek-v4-*；后来 model_name 换成真实模型名 deepseek-flash，
#: key 没跟着改，于是留下一个既不对应任何模型、又让人误以为在跑另一个模型的空壳前缀。
#: 映射是**无条件**的：key 只是「调用方引用名」，改写它不动用户的 provider/model_name/
#: 参数，所以即便用户改过这些旧 key 条目，改名后依然指向同一个模型，不会丢配置。
_LEGACY_DEFAULT_MODEL_KEYS: dict[str, str] = {
    "deepseek-v4-pro": "deepseek-flash-max",
    "deepseek-v4-flash-max": "deepseek-flash-max",
    "deepseek-v4-flash-high": "deepseek-flash-high",
    "deepseek-v4-flash-off": "deepseek-flash-off",
}


@Config.migration(from_version="0.6.0", to_version="0.7.0")
def migrate_v6_to_v7(old: dict) -> dict:
    """迁移 0.6.0 -> 0.7.0：默认对话模型 key 与真实模型名对齐。

    - [[models.registry]] 里旧的 deepseek-v4-* key 改名为 deepseek-flash*；
      已停用的 pro 条目并入 flash（两者本来就是同一模型名 + 同一 max 推理强度）。
    - [models.assignments] 里引用旧 key 的角色同步改指新 key，避免出现
      「引用了模型库里不存在的 key」而让整条角色降级。
    """
    new: dict[str, Any] = {"version": "0.7.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if not isinstance(models, dict):
        return new

    migrated_models: dict[str, Any] = {}
    for name, value in models.items():
        if name not in ("registry", "assignments"):
            migrated_models[name] = value

    registry = models.get("registry")
    renamed: dict[str, str] = {}
    seen_refs: set[str] = set()
    migrated_registry: list[Any] = []
    if isinstance(registry, list):
        for entry in registry:
            if not isinstance(entry, dict):
                migrated_registry.append(entry)
                continue
            # 旧写法 key/description -> 新写法 model_ref/display_name。
            # 两者都是纯改名：provider / model_name / 参数原样保留。
            entry = dict(entry)
            current = str(entry.pop("key", "") or entry.get("model_ref") or "").strip()
            if "description" in entry and "display_name" not in entry:
                entry["display_name"] = entry.pop("description")
            target = _LEGACY_DEFAULT_MODEL_KEYS.get(current)
            if target is not None:
                # pro 与 flash-max 同为 model_name=deepseek-flash + max 推理，指向同一
                # 新引用名；去重后只留一条，否则模型库里会出现两个同模型条目。
                if target in seen_refs:
                    renamed[current] = target
                    continue
                entry["model_ref"] = target
                renamed[current] = target
            else:
                entry["model_ref"] = current
            ref_now = str(entry.get("model_ref") or "").strip()
            if ref_now in seen_refs:
                continue
            if ref_now:
                seen_refs.add(ref_now)
            migrated_registry.append(entry)
    if migrated_registry:
        migrated_models["registry"] = migrated_registry

    assignments = models.get("assignments")
    if isinstance(assignments, dict):
        migrated_assignments: dict[str, Any] = {}
        for role, value in assignments.items():
            if isinstance(value, list):
                migrated_assignments[role] = [
                    renamed.get(str(item).strip(), item) for item in value
                ]
            else:
                text = str(value or "").strip()
                migrated_assignments[role] = renamed.get(text, value)
        migrated_models["assignments"] = migrated_assignments

    if migrated_models:
        new["models"] = migrated_models
    return new
